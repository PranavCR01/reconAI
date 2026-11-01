"""Generate data/scenarios.json: the declared fault (+ confounders) for every known record.

- Benchmark records: fault = the labeled root cause in data/benchmark_ground_truth.json.
  Confounders are assigned deterministically from a hash of the incident id (not by
  hand), so the set is reproducible and not tuned to the graph.
- Demo records: the rows of data/sample_fsc_recon.csv that aren't in the benchmark get
  a declared fault so the demo is coherent. They are marked source="demo" and are
  excluded from accuracy metrics.

Run: python scripts/build_scenarios.py   (rewrites data/scenarios.json)
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUND_TRUTH = ROOT / "data" / "benchmark_ground_truth.json"
SAMPLE_CSV = ROOT / "data" / "sample_fsc_recon.csv"
OUT = ROOT / "data" / "scenarios.json"

# Probability a benchmark incident carries each confounder.
UNRELATED_MISSED_EVENT = 0.35   # noise on the delivery signal (for non-delivery faults)
APEX_DORMANT = 0.30             # Apex conditional logic present but not fired

# Demo rows not covered by the benchmark: chosen to show each kind of outcome once.
DEMO_FAULTS = {
    ("FinancialAccount__c", "AnnualIncome__c", "STALE_VALUE"): ("CDC_FIELD_EXCLUDED", []),
    ("FinancialAccount__c", "AccountStatus__c", "VALUE_MISMATCH"): ("APEX_SUPPRESSION", []),
    ("FinancialAccount__c", "BalanceAmt__c", "MISSING_RECORD"): ("DELIVERY_GAP", ["apex_conditional_dormant"]),
    ("KYC_Record__c", "VerificationStatus__c", "VALUE_MISMATCH"): ("DATAWAVE_TRANSFORM_ERROR", ["unrelated_missed_event"]),
    ("KYC_Record__c", "VerificationStatus__c", "DUPLICATE_DOWNSTREAM"): ("DUPLICATE_DOWNSTREAM", []),
    ("Address__c", "PostalCode", "STALE_VALUE"): ("NO_FAULT_FOUND", []),
    ("Address__c", "StateCode", "NULL_DOWNSTREAM"): ("DOWNSTREAM_OVERWRITE", []),
}


def _unit(*parts: str) -> float:
    """Deterministic number in [0, 1) from the given strings."""
    digest = hashlib.sha256(":".join(parts).encode()).hexdigest()
    return int(digest[:12], 16) / float(16 ** 12)


def benchmark_scenarios() -> list[dict]:
    incidents = json.loads(GROUND_TRUTH.read_text())["incidents"]
    out = []
    for inc in incidents:
        fault = inc["ground_truth"]["root_cause"]
        confounders = []
        if fault != "DELIVERY_GAP" and _unit(inc["id"], "missed") < UNRELATED_MISSED_EVENT:
            confounders.append("unrelated_missed_event")
        if fault != "APEX_SUPPRESSION" and _unit(inc["id"], "apex") < APEX_DORMANT:
            confounders.append("apex_conditional_dormant")
        out.append({"sf_record_id": inc["sf_record_id"], "incident_id": inc["id"], "fault": fault,
                    "confounders": confounders, "source": "benchmark"})
    return out


def demo_scenarios(known: set[str]) -> list[dict]:
    out = []
    for row in csv.DictReader(SAMPLE_CSV.open()):
        if row["sf_record_id"] in known:
            continue
        key = (row["sf_object"], row["sf_field"], row["discrepancy_type"])
        if key not in DEMO_FAULTS:
            raise SystemExit(f"no demo fault declared for {key}")
        fault, confounders = DEMO_FAULTS[key]
        out.append({"sf_record_id": row["sf_record_id"], "fault": fault, "confounders": confounders, "source": "demo"})
    return out


def build() -> dict:
    bench = benchmark_scenarios()
    demo = demo_scenarios({s["sf_record_id"] for s in bench})
    return {
        "version": 1,
        "generated_by": "scripts/build_scenarios.py",
        "confounder_rates": {"unrelated_missed_event": UNRELATED_MISSED_EVENT, "apex_conditional_dormant": APEX_DORMANT},
        "scenarios": bench + demo,
    }


if __name__ == "__main__":
    data = build()
    OUT.write_text(json.dumps(data, indent=1) + "\n")
    n_conf = sum(bool(s["confounders"]) for s in data["scenarios"] if s["source"] == "benchmark")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(data['scenarios'])} scenarios, {n_conf} benchmark incidents with confounders")
