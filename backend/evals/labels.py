"""Dataset loading and retrieval relevance labels.

Retrieval labels: an artifact in the seeded knowledge base (backend/seed/fsc_incidents.py)
is *relevant* to a benchmark incident when its root-cause family matches the incident's
labeled root cause. The family of each artifact is assigned once, below, by reading the
artifact; incidents inherit relevance from their label. This is a documented rule, not an
independent per-pair human judgment, and the report says so. Artifacts whose cause fits no
benchmark category (cache TTL, filter exclusion) are relevant to nothing.

Artifacts are identified by their stable `source` URI (their database ids are random).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GROUND_TRUTH = ROOT / "data" / "benchmark_ground_truth.json"
SCENARIOS = ROOT / "data" / "scenarios.json"

ARTIFACT_FAMILY: dict[str, str | None] = {
    "FLS_blocking": "FLS_STRIPPED",
    "CDC_field_exclusion": "CDC_FIELD_EXCLUDED",
    "Apex_conditional_publish": "APEX_SUPPRESSION",
    "missed_CDC_events": "DELIVERY_GAP",
    "async_consumer_lag": "DELIVERY_GAP",
    "batch_timeout": "DELIVERY_GAP",
    "sync_job_skip": "DELIVERY_GAP",
    "middleware_routing_error": "DELIVERY_GAP",
    "dataweave_mapping_error": "DATAWAVE_TRANSFORM_ERROR",
    "enum_conversion_error": "DATAWAVE_TRANSFORM_ERROR",
    "status_mapping_drift": "DATAWAVE_TRANSFORM_ERROR",
    "transform_error_drop": "DATAWAVE_TRANSFORM_ERROR",
    "idempotency_key_missing": "DUPLICATE_DOWNSTREAM",
    "retry_loop_double_insert": "DUPLICATE_DOWNSTREAM",
    "downstream_overwrite": "DOWNSTREAM_OVERWRITE",
    "cache_TTL_too_long": None,
    "integration_filter_exclusion": None,
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_incidents() -> list[dict]:
    return json.loads(GROUND_TRUTH.read_text())["incidents"]


def relevant_sources(root_cause: str) -> set[str]:
    """Sources of the seeded artifacts relevant to an incident with this labeled root cause."""
    from backend.seed.fsc_incidents import _INCIDENTS

    unmapped = {a.root_cause_category for a in _INCIDENTS} - set(ARTIFACT_FAMILY)
    if unmapped:
        raise ValueError(f"seeded artifacts with no family assigned: {sorted(unmapped)}")
    return {a.source for a in _INCIDENTS if ARTIFACT_FAMILY[a.root_cause_category] == root_cause}
