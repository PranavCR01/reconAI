"""Scenario registry: the simulated "true state of the world" behind each recon row.

The tool simulators (Salesforce, DB2, Splunk) used to draw every signal at random,
independent of the benchmark labels, so diagnostic accuracy only measured how often
random outputs agreed with hand-written labels. A scenario declares the actual fault
for a record plus optional confounders (realistic noise that points elsewhere), and
the simulators produce signals consistent with it. Records without a scenario (live
uploads) keep the simulators' seeded-random behavior.

What this makes measurable: whether the hypothesis graph identifies the declared
fault despite the confounders. It is not real-world accuracy.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

SCENARIO_FILE = Path(__file__).resolve().parents[2] / "data" / "scenarios.json"

FAULTS = (
    "FLS_STRIPPED",              # integration user can't read the field; Salesforce omits it silently
    "CDC_FIELD_EXCLUDED",        # field not tracked by Change Data Capture; no change events published
    "DELIVERY_GAP",              # events published but not delivered/consumed (missed events)
    "DATAWAVE_TRANSFORM_ERROR",  # MuleSoft DataWeave mapping produced the wrong value
    "DUPLICATE_DOWNSTREAM",      # retries + non-idempotent upsert wrote duplicate rows
    "DOWNSTREAM_OVERWRITE",      # value reached DB2, then something downstream cleared it
    "APEX_SUPPRESSION",          # an Apex trigger suppressed the publish for this record
    "NO_FAULT_FOUND",            # every check is clean: the correct outcome is escalation
)

CONFOUNDERS = (
    "unrelated_missed_event",    # one missed event from an unrelated timeout (points at DELIVERY_GAP)
    "apex_conditional_dormant",  # Apex has conditional publish logic that did not fire for this record
)


@dataclass(frozen=True)
class Scenario:
    sf_record_id: str
    fault: str
    confounders: frozenset[str] = field(default_factory=frozenset)
    source: str = "benchmark"  # benchmark | demo | test

    def __post_init__(self):
        if self.fault not in FAULTS:
            raise ValueError(f"unknown fault {self.fault!r}")
        unknown = set(self.confounders) - set(CONFOUNDERS)
        if unknown:
            raise ValueError(f"unknown confounders {sorted(unknown)}")

    def has(self, confounder: str) -> bool:
        return confounder in self.confounders


_lock = threading.Lock()
_registry: dict[str, Scenario] | None = None


def _load(path: Path = SCENARIO_FILE) -> dict[str, Scenario]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {
        s["sf_record_id"]: Scenario(s["sf_record_id"], s["fault"], frozenset(s.get("confounders", [])), s.get("source", "benchmark"))
        for s in raw["scenarios"]
    }


def registry() -> dict[str, Scenario]:
    global _registry
    with _lock:
        if _registry is None:
            _registry = _load()
        return _registry


def lookup(sf_record_id: str | None) -> Scenario | None:
    if not sf_record_id:
        return None
    return registry().get(sf_record_id)


def set_registry(scenarios: dict[str, Scenario] | None) -> None:
    """Replace the registry (tests); None reloads from the scenario file on next use."""
    global _registry
    with _lock:
        _registry = scenarios
