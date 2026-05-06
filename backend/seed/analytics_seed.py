"""Seed 30 days of synthetic analytics data into Supabase.

Idempotent: skips if > 10 recon_runs already exist.
Run with:  python -m backend.seed.analytics_seed
"""
from __future__ import annotations

import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

RNG = random.Random(42)

DISC_TYPES = [
    ("NULL_DOWNSTREAM", 0.32),
    ("VALUE_MISMATCH", 0.27),
    ("STALE_VALUE", 0.17),
    ("MISSING_RECORD", 0.14),
    ("DUPLICATE_DOWNSTREAM", 0.10),
]
DISC_NAMES = [d[0] for d in DISC_TYPES]
DISC_WEIGHTS = [d[1] for d in DISC_TYPES]

SEVERITIES = [("P1", 0.10), ("P2", 0.40), ("P3", 0.50)]
SEV_NAMES = [s[0] for s in SEVERITIES]
SEV_WEIGHTS = [s[1] for s in SEVERITIES]

SF_OBJECTS = ["Account", "Contact", "FinancialAccount__c", "KYC_Record__c", "Address__c", "Asset", "Lead"]
SF_FIELDS = ["AccountNumber", "TaxId", "Balance", "KYCStatus", "PostalCode", "SerialNo", "LeadSource"]

ROOT_CAUSES = [
    ("FLS_STRIPPED", 0.34),
    ("CDC_EXCLUDED", 0.22),
    ("DATAWAVE_ERROR", 0.18),
    ("DELIVERY_GAP", 0.14),
    ("UNKNOWN", 0.12),
]
RC_NAMES = [r[0] for r in ROOT_CAUSES]
RC_WEIGHTS = [r[1] for r in ROOT_CAUSES]

FIX_TYPES = ["fls_permission_grant", "dataweave_mapping_fix", "cdc_channel_config", "delivery_gap", "other"]
FIX_WEIGHTS = [0.34, 0.22, 0.18, 0.14, 0.12]

ORIGIN = datetime(2026, 4, 6, 0, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 5, 4, 23, 59, 59, tzinfo=timezone.utc)

# Days that should spike (0-indexed from ORIGIN)
SPIKE_DAYS = {16, 20, 23}  # Apr 22, Apr 26, Apr 29

DEPLOYMENTS = [
    {"deploy_name": "mule-acct-out@v3.3.0",   "deployed_at": "2026-04-08T10:30:00+00:00", "deploy_type": "mulesoft",    "description": "MuleSoft account outbound v3.3.0 — minor mapping update"},
    {"deploy_name": "cdc-pipeline@v2.18.0",    "deployed_at": "2026-04-11T06:00:00+00:00", "deploy_type": "mulesoft",    "description": "CDC pipeline v2.18.0 — CloudHub runtime upgrade"},
    {"deploy_name": "db2-DDL-2026-04-15",      "deployed_at": "2026-04-15T22:00:00+00:00", "deploy_type": "db2",         "description": "DB2 DDL — FSC.PARTY_ADDR schema extension"},
    {"deploy_name": "mule-contact@v4.1.2",     "deployed_at": "2026-04-19T09:15:00+00:00", "deploy_type": "mulesoft",    "description": "MuleSoft contact sync v4.1.2 — fsc-contact-sync"},
    {"deploy_name": "db2-DDL-2026-04-22",      "deployed_at": "2026-04-22T18:30:00+00:00", "deploy_type": "db2",         "description": "DB2 DDL — FSC.PARTY_TAX_ID schema change (SPIKE)"},
    {"deploy_name": "mule-acct-out@v3.4.1",   "deployed_at": "2026-04-26T14:02:00+00:00", "deploy_type": "mulesoft",    "description": "MuleSoft acct-out v3.4.1 — fsc-mappings acct-out.dwl (SPIKE)"},
    {"deploy_name": "SEC-4432",                "deployed_at": "2026-04-29T03:11:00+00:00", "deploy_type": "salesforce",  "description": "Profile · PII tightening — SEC-4432 compliance (SPIKE)"},
    {"deploy_name": "cloudhub-runtime@v4.0.3", "deployed_at": "2026-05-02T08:00:00+00:00", "deploy_type": "infra",       "description": "CloudHub runtime v4.0.3 — platform maintenance"},
]


def _chunk(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _gauss(mu: float, sigma: float, lo: float, hi: float) -> float:
    return _clamp(RNG.gauss(mu, sigma), lo, hi)


def main():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    client = create_client(url, key)

    # Idempotency check
    count_result = client.table("recon_runs").select("id", count="exact").execute()
    existing = count_result.count or 0
    if existing > 10:
        print(f"Skipping seed — {existing} recon_runs already exist (threshold: 10)")
        return

    print("Seeding analytics data…")

    # --- recon_runs ---
    runs = []
    run_day_map: dict[int, list[str]] = {}  # day_index -> [run_id, ...]

    day_index = 0
    current_day = ORIGIN
    while current_day <= END:
        d = day_index
        is_spike = d in SPIKE_DAYS
        n_runs = 2 if is_spike else 1
        for _ in range(n_runs):
            run_id = str(uuid.uuid4())
            created = current_day + timedelta(hours=RNG.randint(1, 20))
            row_count = RNG.randint(20, 28) if is_spike else RNG.randint(8, 14)
            runs.append({
                "id": run_id,
                "run_date": current_day.date().isoformat(),
                "triggered_by": "scheduled-job",
                "sf_org_id": "sf-fsc-prod-01",
                "db2_environment": "PROD" if RNG.random() > 0.3 else "UAT",
                "total_rows_checked": row_count,
                "total_discrepancies": row_count,
                "status": "complete",
                "created_at": created.isoformat(),
                "completed_at": (created + timedelta(minutes=RNG.randint(3, 12))).isoformat(),
            })
            run_day_map.setdefault(d, []).append(run_id)
        current_day += timedelta(days=1)
        day_index += 1

    for batch in _chunk(runs, 50):
        client.table("recon_runs").insert(batch).execute()
    print(f"  Inserted {len(runs)} recon_runs")

    # --- recon_rows ---
    rows = []
    row_run_day: dict[str, int] = {}  # row_id -> day_index

    for d, run_ids in run_day_map.items():
        is_spike = d in SPIKE_DAYS
        for run_id in run_ids:
            n_rows = RNG.randint(20, 28) if is_spike else RNG.randint(8, 14)
            for _ in range(n_rows):
                row_id = str(uuid.uuid4())
                obj_idx = RNG.randint(0, len(SF_OBJECTS) - 1)
                disc = RNG.choices(DISC_NAMES, weights=DISC_WEIGHTS, k=1)[0]
                sev = RNG.choices(SEV_NAMES, weights=SEV_WEIGHTS, k=1)[0]
                rows.append({
                    "id": row_id,
                    "run_id": run_id,
                    "sf_object": SF_OBJECTS[obj_idx],
                    "sf_field": SF_FIELDS[obj_idx],
                    "sf_record_id": f"001{RNG.randint(100000, 999999)}AAA",
                    "sf_value": str(RNG.randint(100, 9999)),
                    "db2_table": f"FSC_{SF_OBJECTS[obj_idx].upper().replace('__C', '')}",
                    "db2_column": SF_FIELDS[obj_idx].upper(),
                    "db2_value": str(RNG.randint(100, 9999)),
                    "discrepancy_type": disc,
                    "severity": sev,
                    "created_at": (ORIGIN + timedelta(days=d)).isoformat(),
                })
                row_run_day[row_id] = d

    for batch in _chunk(rows, 50):
        client.table("recon_rows").insert(batch).execute()
    print(f"  Inserted {len(rows)} recon_rows")

    # --- rca_incidents ---
    incidents = []
    incident_ids = []
    row_to_incident: dict[str, str] = {}

    for row in rows:
        inc_id = str(uuid.uuid4())
        confidence = round(_gauss(0.85, 0.06, 0.72, 0.97), 3)
        rc = RNG.choices(RC_NAMES, weights=RC_WEIGHTS, k=1)[0]
        d = row_run_day[row["id"]]
        created = ORIGIN + timedelta(days=d, hours=RNG.randint(1, 22))
        incidents.append({
            "id": inc_id,
            "recon_row_id": row["id"],
            "hypotheses_tested": ["H1", "H2"],
            "hypotheses_ruled_out": ["H1"],
            "final_hypothesis": "H2",
            "confidence": confidence,
            "similar_incidents": [],
            "similarity_scores": [],
            "root_cause_summary": rc,
            "suggested_fix": f"Apply {rc.lower().replace('_', ' ')} fix",
            "requires_human_review": confidence < 0.75,
            "status": "complete",
            "llm_model": "claude-haiku-4-5",
            "total_tool_calls": RNG.randint(3, 6),
            "total_tokens_used": RNG.randint(1200, 2100),
            "latency_ms": RNG.randint(8000, 18000),
            "created_at": created.isoformat(),
        })
        incident_ids.append(inc_id)
        row_to_incident[row["id"]] = inc_id

    for batch in _chunk(incidents, 50):
        client.table("rca_incidents").insert(batch).execute()
    print(f"  Inserted {len(incidents)} rca_incidents")

    # --- resolutions (~60% rate, 85% ai_was_correct) ---
    resolutions = []
    resolve_sample = RNG.sample(incident_ids, k=int(len(incident_ids) * 0.60))

    for inc_id in resolve_sample:
        fix = RNG.choices(FIX_TYPES, weights=FIX_WEIGHTS, k=1)[0]
        ai_correct = RNG.random() < 0.85
        resolutions.append({
            "id": str(uuid.uuid4()),
            "incident_id": inc_id,
            "confirmed_root_cause": RNG.choices(RC_NAMES, weights=RC_WEIGHTS, k=1)[0],
            "fix_applied": f"Applied {fix.replace('_', ' ')}",
            "fix_type": fix,
            "fix_verified": True,
            "ai_was_correct": ai_correct,
            "resolved_by": "recon-analyst",
            "resolved_at": (datetime.now(timezone.utc) - timedelta(days=RNG.randint(0, 25))).isoformat(),
        })

    for batch in _chunk(resolutions, 50):
        client.table("resolutions").insert(batch).execute()
    print(f"  Inserted {len(resolutions)} resolutions")

    # --- deployment_events ---
    for dep in DEPLOYMENTS:
        client.table("deployment_events").insert({
            "id": str(uuid.uuid4()),
            "deploy_name": dep["deploy_name"],
            "deployed_at": dep["deployed_at"],
            "deploy_type": dep["deploy_type"],
            "description": dep["description"],
            "affected_org": "sf-fsc-prod-01",
        }).execute()
    print(f"  Inserted {len(DEPLOYMENTS)} deployment_events")

    print("Seed complete.")


if __name__ == "__main__":
    main()
