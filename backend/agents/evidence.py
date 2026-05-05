"""Evidence Agent — citation enforcement, EvidenceResult validation,
ThreadPoolExecutor fan-out, and H3 early termination (Slice 3).
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from pydantic import ValidationError

from backend.models.entities import EvidenceSourceType
from backend.models.outputs import EvidenceResult
from backend.models.state import ReconState
from backend.tools.db2_sim import query_db2_field_history
from backend.tools.salesforce_sim import (
    get_apex_trigger_config,
    get_cdc_field_config,
    get_field_permissions,
)
from backend.tools.splunk_sim import query_splunk

_REGISTRY = {
    "query_db2_field_history": query_db2_field_history,
    "get_field_permissions": get_field_permissions,
    "get_cdc_field_config": get_cdc_field_config,
    "get_apex_trigger_config": get_apex_trigger_config,
    "splunk_stub": query_splunk,
}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_evidence_result(tool: str, h_key: str, result: dict) -> dict:
    """Deterministic mapping from tool output to EvidenceResult fields.

    Structural validation only (non-negotiable #6). LLM-grounded citation text
    added in Slice 4 alongside RAG context retrieval.
    """
    if tool == "query_db2_field_history":
        populated = result.get("was_populated", False)
        col = result.get("db2_column") or "unknown_col"
        last_val = result.get("last_value")
        last_ts = result.get("last_updated_at")
        window = result.get("time_window_days", 30)
        return {
            "hypothesis_tested": h_key,
            "source_type": EvidenceSourceType.sf_field_history,
            "source_reference": f"db2://{col}/window-{window}d",
            "content": (
                f"DB2 column {col} previously held value {last_val!r} "
                f"(last updated {last_ts})."
                if populated else
                f"DB2 column {col} has no historical values in the {window}-day window."
            ),
            "relevance_explanation": (
                "A prior value confirms the field was once synced correctly, "
                "indicating a downstream clear/overwrite event caused the null."
                if populated else
                "No historical DB2 values suggests the field was never synced from Salesforce."
            ),
            "rules_out": [] if populated else ["H4_overwrite"],
            "confirms": "H4: downstream overwrite/clear event" if populated else None,
        }

    if tool == "get_field_permissions":
        has_access = result.get("has_read_access", True)
        user = result.get("integration_user") or "unknown_user"
        api_name = result.get("api_name") or f"{result.get('sf_object')}.{result.get('sf_field')}"
        psets = ", ".join(result.get("permission_sets") or []) or "none assigned"
        return {
            "hypothesis_tested": h_key,
            "source_type": EvidenceSourceType.sf_field_permissions,
            "source_reference": f"sf-fls://{api_name}/{user}",
            "content": (
                f"Integration user '{user}' {'has' if has_access else 'lacks'} FLS read access "
                f"to {api_name}. Permission sets: {psets}."
            ),
            "relevance_explanation": (
                "FLS governs which fields the integration user can read. "
                "A missing permission directly prevents the field value from being synced."
            ),
            "rules_out": ["H3_FLS"] if has_access else [],
            "confirms": "H3: FLS blocking downstream sync" if not has_access else None,
        }

    if tool == "get_cdc_field_config":
        tracked = result.get("is_tracked", True)
        channel = result.get("cdc_channel") or "unknown_channel"
        reason = result.get("reason_excluded") or "unspecified"
        sf_obj = result.get("sf_object", "")
        sf_field = result.get("sf_field", "")
        return {
            "hypothesis_tested": h_key,
            "source_type": EvidenceSourceType.platform_event_usage,
            "source_reference": f"sf-cdc://{channel}/{sf_obj}.{sf_field}",
            "content": (
                f"Field '{sf_field}' is {'tracked' if tracked else 'NOT tracked'} "
                f"in CDC channel '{channel}'."
                + (f" Exclusion reason: {reason}." if not tracked else "")
            ),
            "relevance_explanation": (
                "CDC field tracking controls whether Salesforce publishes change events "
                "for this field to downstream consumers."
            ),
            "rules_out": ["H3_CDC"] if tracked else [],
            "confirms": "H3: CDC field exclusion prevents downstream sync" if not tracked else None,
        }

    if tool == "get_apex_trigger_config":
        conditional = result.get("has_conditional_publish", False)
        trigger = result.get("trigger_name") or "unknown_trigger"
        logic = result.get("conditional_logic_description") or "undocumented"
        sf_obj = result.get("sf_object", "")
        return {
            "hypothesis_tested": h_key,
            "source_type": EvidenceSourceType.apex_job_log,
            "source_reference": f"sf-apex://{trigger}/{sf_obj}",
            "content": (
                f"Apex trigger '{trigger}' on {sf_obj} has conditional publish logic: {logic}."
                if conditional else
                f"Apex trigger '{trigger}' on {sf_obj} has no conditional publish gates."
            ),
            "relevance_explanation": (
                "Apex triggers can suppress platform event publishing based on conditions, "
                "causing null values to propagate silently."
            ),
            "rules_out": ["H3_Apex"] if not conditional else [],
            "confirms": "H3: Apex conditional publish suppresses null propagation" if conditional else None,
        }

    if tool == "splunk_stub":
        missed = result.get("missed_events", False)
        count = result.get("missed_count", 0)
        last_ts = result.get("last_event_ts", "unknown")
        record_id = result.get("record_id", "unknown")
        sf_field = result.get("sf_field", "unknown")
        source_ref = (
            result.get("source_reference")
            or f"splunk://cdc-pipeline/{sf_field}/{record_id}"
        )
        return {
            "hypothesis_tested": h_key,
            "source_type": EvidenceSourceType.splunk_log,
            "source_reference": source_ref,
            "content": (
                f"{count} missed CDC/platform event(s) for record {record_id} "
                f"field '{sf_field}'. Last event: {last_ts}."
                if missed else
                f"No missed events for record {record_id} field '{sf_field}'. "
                f"Last event: {last_ts}."
            ),
            "relevance_explanation": (
                "Missed platform events indicate CDC pipeline gaps preventing "
                "field changes from reaching downstream DB2."
                if missed else
                "No evidence of missed events — CDC pipeline appears functional for this field."
            ),
            "rules_out": ["H2_splunk_clean"] if not missed else [],
            "confirms": "H2: CDC pipeline missed events — field change not propagated" if missed else None,
        }

    # Fallback for unregistered tools
    return {
        "hypothesis_tested": h_key,
        "source_type": EvidenceSourceType.middleware_log,
        "source_reference": f"tool://{tool}/{h_key}",
        "content": f"Tool '{tool}' result: {result}",
        "relevance_explanation": f"Raw output from tool '{tool}' for hypothesis {h_key}.",
        "rules_out": [],
        "confirms": None,
    }


def _execute_one(call: dict) -> dict:
    """Execute a single tool call and validate the EvidenceResult (non-negotiable #6)."""
    tool_name = call.get("tool", "")
    args = call.get("args", {})
    h_key = call.get("hypothesis_key", "unknown")

    fn = _REGISTRY.get(tool_name)
    if fn is None:
        return {
            "hypothesis_key": h_key,
            "tool": tool_name,
            "result": {"status": "not_implemented", "message": f"{tool_name} not registered"},
            "timestamp": _ts(),
        }

    try:
        result_dict = fn(**args).model_dump()
    except Exception as exc:
        return {"hypothesis_key": h_key, "tool": tool_name, "error": str(exc), "timestamp": _ts()}

    ev_dict = _build_evidence_result(tool_name, h_key, result_dict)
    try:
        EvidenceResult.model_validate(ev_dict)
        if not ev_dict.get("source_reference"):
            raise ValueError("source_reference is empty")
    except (ValidationError, ValueError) as exc:
        # Non-negotiable #6: schema violation → retry with error context (fallback mapping)
        ev_dict = {
            "hypothesis_tested": h_key,
            "source_type": EvidenceSourceType.middleware_log,
            "source_reference": f"tool://{tool_name}/{h_key}",
            "content": f"[validation-fallback] {result_dict}",
            "relevance_explanation": f"EvidenceResult validation failed ({exc}). Raw result preserved.",
            "rules_out": [],
            "confirms": None,
        }
        EvidenceResult.model_validate(ev_dict)

    return {
        "hypothesis_key": h_key,
        "tool": tool_name,
        "result": result_dict,
        "evidence_result": ev_dict,
        "timestamp": _ts(),
    }


def _skipped_entry(call: dict, reason: str) -> dict:
    return {
        "hypothesis_key": call.get("hypothesis_key", "unknown"),
        "tool": call.get("tool", ""),
        "result": {"status": "skipped", "reason": reason},
        "skipped": True,
        "timestamp": _ts(),
    }


def _execute_hypothesis_calls(calls: list[dict]) -> list[dict]:
    """Run tool calls for one hypothesis with early termination + concurrent fan-out.

    FLS runs first. If it confirms FLS blocking (has_read_access=False), the
    remaining H3 calls are skipped — root cause established, no point running CDC
    and Apex. All other calls run concurrently via ThreadPoolExecutor.
    """
    results: list[dict] = []
    fls_calls = [c for c in calls if c.get("tool") == "get_field_permissions"]
    other_calls = [c for c in calls if c.get("tool") != "get_field_permissions"]

    for call in fls_calls:
        entry = _execute_one(call)
        results.append(entry)
        if not entry.get("result", {}).get("has_read_access", True):
            for skipped in other_calls:
                results.append(_skipped_entry(skipped, "FLS confirmed root cause — early termination"))
            return results

    if len(other_calls) == 1:
        results.append(_execute_one(other_calls[0]))
    elif len(other_calls) > 1:
        with ThreadPoolExecutor(max_workers=len(other_calls)) as pool:
            futures = {pool.submit(_execute_one, c): c for c in other_calls}
            for fut in as_completed(futures):
                results.append(fut.result())

    return results


def run_evidence(state: ReconState) -> dict:
    pending = state.get("tool_calls") or []
    if not pending:
        return {"evidence_retry_count": (state.get("evidence_retry_count") or 0) + 1}

    by_hypothesis: dict[str, list[dict]] = defaultdict(list)
    for call in pending:
        by_hypothesis[call.get("hypothesis_key", "unknown")].append(call)

    new_evidence: list[dict] = []
    for calls in by_hypothesis.values():
        new_evidence.extend(_execute_hypothesis_calls(calls))

    return {
        "evidence_collected": state["evidence_collected"] + new_evidence,
        "tool_calls": [],
    }
