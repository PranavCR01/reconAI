"""Declarative hypothesis catalogue: what the graph checks, in what order, and how a
tool result confirms, refutes, or leaves a hypothesis inconclusive.

Each hypothesis is exactly one check (one tool) with a pure rule over that tool's
output and a declared confidence. The engine in backend/agents/hypothesis.py walks
the list for a discrepancy type and stops at the first confirmed hypothesis.

Ordering principles (domain logic, not fitted to benchmark labels):
1. Configuration facts before symptoms. A stripped field (FLS) or an untracked field
   (CDC) *causes* missing/odd events downstream, so those checks run before the
   delivery check; a missed event alone can be unrelated noise.
2. Record-level facts over code that merely exists. Apex conditional publish logic
   only counts if it actually suppressed this record's publish.
3. Checks only where the mechanism can produce the symptom. FLS strips fields, not
   whole records, so it isn't a MISSING_RECORD hypothesis.
4. Confidence < 0.75 on a confirmed hypothesis still sends the incident to review
   (Apex suppression is often intentional business logic a human should judge).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

GRAPH_VERSION = "2.0.0"

# Root-cause categories (match data/benchmark_ground_truth.json plus two the labels never use).
CATEGORIES = (
    "FLS_STRIPPED", "CDC_FIELD_EXCLUDED", "DELIVERY_GAP", "DATAWAVE_TRANSFORM_ERROR",
    "DUPLICATE_DOWNSTREAM", "DOWNSTREAM_OVERWRITE", "APEX_SUPPRESSION",
)

# What kind of check a hypothesis runs; used to compare paths with the labels, which
# were written against an older naming scheme (H1/H2/H3a/H3b/H4).
LABEL_KIND = {"H1": "db2_history", "H2": "delivery", "H3a": "fls", "H3b": "cdc", "H4": "dataweave",
              "HDD1": "retries", "HDD2": "duplicate_rows"}

# (confirmed|refuted|inconclusive, reason, root-cause text if confirmed, confidence override or None)
Verdict = tuple[str, str, "str | None", "float | None"]


def _integration_user(row: dict) -> str:
    return row.get("sf_modified_by") or "sf-integration@org.com"


def _field(row: dict) -> str:
    return f"{row.get('sf_object')}.{row.get('sf_field')}"


# -- tool argument builders ---------------------------------------------------
def _db2_args(row):
    return {"sf_object": row["sf_object"], "sf_field": row["sf_field"], "sf_record_id": row["sf_record_id"]}


def _splunk_args(row):
    return {"sf_record_id": row["sf_record_id"], "sf_field": row["sf_field"], "sf_object": row["sf_object"]}


def _fls_args(row):
    return {"integration_user": _integration_user(row), "sf_object": row["sf_object"],
            "sf_field": row["sf_field"], "sf_record_id": row["sf_record_id"]}


def _cdc_args(row):
    return {"sf_object": row["sf_object"], "sf_field": row["sf_field"], "sf_record_id": row["sf_record_id"]}


def _apex_args(row):
    return {"sf_object": row["sf_object"], "sf_record_id": row["sf_record_id"]}


# -- rules: tool result -> verdict -------------------------------------------
def _overwrite_rule(r: dict, row: dict) -> Verdict:
    if r.get("was_populated"):
        return ("confirmed", f"DB2 held {r.get('last_value')!r} on {r.get('last_updated_at')}",
                f"{_field(row)} reached DB2 (value {r.get('last_value')!r} as of {r.get('last_updated_at')}) "
                f"and was later cleared downstream by an overwrite or null-propagation event.", None)
    return ("refuted", f"no prior value in DB2 within {r.get('time_window_days', 30)} days", None, None)


def _fls_rule(r: dict, row: dict) -> Verdict:
    if r.get("has_read_access") is False:
        psets = ", ".join(r.get("permission_sets") or []) or "none assigned"
        return ("confirmed", f"integration user {r.get('integration_user')} lacks read access",
                f"Integration user '{r.get('integration_user')}' lacks field-level read access to {_field(row)} "
                f"(permission sets: {psets}), so Salesforce silently omits the field from the integration's reads.", None)
    return ("refuted", f"integration user {r.get('integration_user')} can read the field", None, None)


def _cdc_rule(r: dict, row: dict) -> Verdict:
    if r.get("is_tracked") is False:
        return ("confirmed", f"field not tracked in CDC ({r.get('reason_excluded') or 'reason unknown'})",
                f"{_field(row)} is excluded from Change Data Capture (channel {r.get('cdc_channel') or 'unknown'}, "
                f"reason: {r.get('reason_excluded') or 'unknown'}), so changes are never published downstream.", None)
    return ("refuted", f"field tracked in {r.get('cdc_channel')}", None, None)


def _apex_rule(r: dict, row: dict) -> Verdict:
    if r.get("suppressed_for_record"):
        return ("confirmed", f"{r.get('trigger_name')} suppressed the publish for this record",
                f"Apex trigger '{r.get('trigger_name')}' skipped the publish for record {row.get('sf_record_id')}: "
                f"{r.get('conditional_logic_description') or 'conditional logic'}.", None)
    if r.get("has_conditional_publish"):
        return ("refuted", f"{r.get('trigger_name')} has conditional logic, but it did not fire for this record", None, None)
    return ("refuted", "no conditional publish logic", None, None)


def _delivery_rule(r: dict, row: dict) -> Verdict:
    if r.get("missed_events"):
        count = r.get("missed_count") or 0
        # A single missed event can be unrelated noise (a one-off timeout); it can't be told
        # apart from a real gap, so it confirms only at review-level confidence.
        confidence = None if count >= 2 else 0.70
        return ("confirmed", f"{count} missed event(s)" + ("" if count >= 2 else " (single event: weak evidence)"),
                f"Splunk shows {count} published event(s) for {_field(row)} on record "
                f"{row.get('sf_record_id')} that were never delivered downstream (last event {r.get('last_event_ts')}).",
                confidence)
    return ("refuted", "all published events were delivered", None, None)


def _dataweave_rule(r: dict, row: dict) -> Verdict:
    if (r.get("transform_errors") or 0) > 0:
        return ("confirmed", f"{r.get('transform_errors')} DataWeave transform error(s)",
                f"MuleSoft logged {r.get('transform_errors')} DataWeave transform error(s) for {_field(row)} on record "
                f"{row.get('sf_record_id')}; the mapping wrote a wrong value to DB2.", None)
    return ("refuted", "no transform errors logged", None, None)


def _retry_rule(r: dict, row: dict) -> Verdict:
    if (r.get("retry_count") or 0) >= 2:
        return ("confirmed", f"{r.get('retry_count')} middleware retries",
                f"Middleware retried delivery of record {row.get('sf_record_id')} {r.get('retry_count')} times; "
                f"each retry inserted a new row because the DB2 write is not idempotent (INSERT, not MERGE on SalesforceId).", None)
    return ("refuted", "no repeated deliveries", None, None)


def _duplicate_rows_rule(r: dict, row: dict) -> Verdict:
    if (r.get("duplicate_rows") or 1) > 1:
        return ("confirmed", f"{r.get('duplicate_rows')} rows for one Salesforce ID",
                f"DB2 holds {r.get('duplicate_rows')} rows for Salesforce ID {row.get('sf_record_id')}: the upsert "
                f"lacks an idempotency key, so repeated writes create duplicates.", None)
    return ("refuted", "one row per Salesforce ID", None, None)


@dataclass(frozen=True)
class Hypothesis:
    id: str
    label: str
    kind: str
    category: str
    tool: str
    args: Callable[[dict], dict]
    rule: Callable[[dict, dict], Verdict]
    confidence: float


def _h(id, label, kind, category, tool, args, rule, confidence):
    return Hypothesis(id, label, kind, category, tool, args, rule, confidence)


CATALOGUE: dict[str, list[Hypothesis]] = {
    "NULL_DOWNSTREAM": [
        _h("H1", "Value reached DB2, then was cleared downstream", "db2_history", "DOWNSTREAM_OVERWRITE",
           "query_db2_field_history", _db2_args, _overwrite_rule, 0.82),
        _h("H3a", "Integration user can't read the field (FLS)", "fls", "FLS_STRIPPED",
           "get_field_permissions", _fls_args, _fls_rule, 0.90),
        _h("H3b", "Field excluded from Change Data Capture", "cdc", "CDC_FIELD_EXCLUDED",
           "get_cdc_field_config", _cdc_args, _cdc_rule, 0.88),
        _h("H3c", "Apex trigger suppressed the publish", "apex", "APEX_SUPPRESSION",
           "get_apex_trigger_config", _apex_args, _apex_rule, 0.72),
        _h("H2", "Published events were not delivered", "delivery", "DELIVERY_GAP",
           "splunk_stub", _splunk_args, _delivery_rule, 0.84),
    ],
    "VALUE_MISMATCH": [
        _h("HVM1", "Integration user can't read the field (FLS)", "fls", "FLS_STRIPPED",
           "get_field_permissions", _fls_args, _fls_rule, 0.85),
        _h("HVM2", "DataWeave transform wrote a wrong value", "dataweave", "DATAWAVE_TRANSFORM_ERROR",
           "splunk_stub", _splunk_args, _dataweave_rule, 0.86),
        _h("HVM3", "Field excluded from Change Data Capture", "cdc", "CDC_FIELD_EXCLUDED",
           "get_cdc_field_config", _cdc_args, _cdc_rule, 0.85),
        _h("HVM4", "Apex trigger suppressed the publish", "apex", "APEX_SUPPRESSION",
           "get_apex_trigger_config", _apex_args, _apex_rule, 0.72),
    ],
    "STALE_VALUE": [
        _h("HSV1", "Field excluded from Change Data Capture", "cdc", "CDC_FIELD_EXCLUDED",
           "get_cdc_field_config", _cdc_args, _cdc_rule, 0.87),
        _h("HSV2", "Published updates were not delivered", "delivery", "DELIVERY_GAP",
           "splunk_stub", _splunk_args, _delivery_rule, 0.84),
    ],
    "MISSING_RECORD": [
        _h("HMR1", "Apex trigger suppressed the record's publish", "apex", "APEX_SUPPRESSION",
           "get_apex_trigger_config", _apex_args, _apex_rule, 0.72),
        _h("HMR2", "Record's events were not delivered", "delivery", "DELIVERY_GAP",
           "splunk_stub", _splunk_args, _delivery_rule, 0.84),
    ],
    "DUPLICATE_DOWNSTREAM": [
        _h("HDD1", "Retries re-inserted the record", "retries", "DUPLICATE_DOWNSTREAM",
           "splunk_stub", _splunk_args, _retry_rule, 0.85),
        _h("HDD2", "Non-idempotent upsert wrote duplicate rows", "duplicate_rows", "DUPLICATE_DOWNSTREAM",
           "query_db2_field_history", _db2_args, _duplicate_rows_rule, 0.80),
    ],
}

BY_ID: dict[str, Hypothesis] = {h.id: h for plan in CATALOGUE.values() for h in plan}
assert len(BY_ID) == sum(len(p) for p in CATALOGUE.values()), "hypothesis ids must be unique"

OUTCOME = {"confirmed": "supports", "refuted": "refutes", "inconclusive": "neutral"}


def evaluate(hypothesis: Hypothesis, raw_result: dict | None, row: dict) -> Verdict:
    """Apply a hypothesis rule; no usable tool result means inconclusive (never refuted)."""
    if not raw_result or raw_result.get("status") in ("not_implemented", "skipped"):
        return ("inconclusive", "the check could not run", None, None)
    return hypothesis.rule(raw_result, row)
