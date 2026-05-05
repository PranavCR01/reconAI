from __future__ import annotations

from backend.config import AgentConfig
from backend.models.outputs import HypothesisDecision
from backend.models.state import ReconState


class HypothesisAgent:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def run(self, state: ReconState) -> dict:
        row = state["recon_row"]
        dt = row.get("discrepancy_type")
        iterations = state["iterations"] + 1
        deploy_note = (
            " [⚠️ Deployment correlation within 24h — consider as contributing factor]"
            if row.get("deployment_correlated") else ""
        )

        if dt == "NULL_DOWNSTREAM":
            return self._null_downstream(state, iterations, deploy_note)
        if dt == "VALUE_MISMATCH":
            return self._value_mismatch(state, iterations, deploy_note)
        if dt == "STALE_VALUE":
            return self._stale_value(state, iterations, deploy_note)
        if dt == "MISSING_RECORD":
            return self._missing_record(state, iterations, deploy_note)
        if dt == "DUPLICATE_DOWNSTREAM":
            return self._duplicate_downstream(state, iterations, deploy_note)

        # Unknown discrepancy type — route to human review without tool calls
        return {
            "current_hypothesis": f"UNKNOWN: {dt} — no graph path defined",
            "tool_calls": [],
            "requires_human_review": True,
            "iterations": iterations,
        }

    def _null_downstream(self, state: ReconState, iterations: int, note: str) -> dict:
        tested = state["hypotheses_tested"]
        evidence = state["evidence_collected"]
        row = state["recon_row"]

        # ── H1: DB2 field history ──────────────────────────────────────────────
        if "H1" not in tested:
            HypothesisDecision(
                next_hypothesis="H1: Verify if field was ever populated in DB2",
                tools_to_call=["query_db2_field_history"],
                reasoning=f"Field is null downstream. Check if DB2 ever held a value.{note}",
                terminate=False,
            )
            return {
                "current_hypothesis": "H1: Verify if field was ever populated in DB2",
                "hypotheses_tested": tested + ["H1"],
                "tool_calls": [{
                    "tool": "query_db2_field_history",
                    "args": {
                        "sf_object": row["sf_object"],
                        "sf_field": row["sf_field"],
                        "sf_record_id": row["sf_record_id"],
                    },
                    "hypothesis_key": "H1",
                }],
                "iterations": iterations,
            }

        # Evaluate H1
        h1 = next((e for e in evidence if e.get("hypothesis_key") == "H1"), None)
        if h1 and h1.get("result", {}).get("was_populated"):
            r = h1["result"]
            root = (
                f"Field '{row['sf_field']}' previously held value '{r.get('last_value')}' "
                f"in DB2 (as of {r.get('last_updated_at')}). A subsequent overwrite or "
                f"null-propagation event cleared it downstream."
            )
            d = HypothesisDecision(
                next_hypothesis="H4: Overwrite/clear event confirmed",
                tools_to_call=[],
                reasoning=root + note,
                terminate=True,
                root_cause=root,
                confidence=0.82,
            )
            return {
                "current_hypothesis": d.next_hypothesis,
                "hypotheses_tested": tested if "H4" in tested else tested + ["H4"],
                "root_cause": d.root_cause,
                "confidence": d.confidence,
                "requires_human_review": False,
                "tool_calls": [],
                "iterations": iterations,
            }

        # ── H2: Splunk triage for missed CDC/platform events ─────────────────
        if "H2" not in tested:
            HypothesisDecision(
                next_hypothesis="H2: Splunk triage for missed CDC/platform events",
                tools_to_call=["splunk_stub"],
                reasoning=f"H1 inconclusive. Checking Splunk for missed events.{note}",
                terminate=False,
            )
            return {
                "current_hypothesis": "H2: Splunk triage for missed CDC/platform events",
                "hypotheses_tested": tested + ["H2"],
                "tool_calls": [{
                    "tool": "splunk_stub",
                    "args": {
                        "sf_record_id": row["sf_record_id"],
                        "sf_field": row["sf_field"],
                        "sf_object": row["sf_object"],
                    },
                    "hypothesis_key": "H2",
                }],
                "iterations": iterations,
            }

        # ── Evaluate H2 Splunk ───────────────────────────────────────────────
        h2 = next((e for e in evidence if e.get("hypothesis_key") == "H2"), None)
        if h2:
            h2_result = h2.get("result", {})
            if h2_result.get("missed_events"):
                missed_count = h2_result.get("missed_count", 0)
                last_ts = h2_result.get("last_event_ts", "unknown")
                root = (
                    f"Splunk detected {missed_count} missed CDC/platform event(s) for "
                    f"'{row['sf_field']}' on record {row['sf_record_id']}. "
                    f"Last observed event: {last_ts}. "
                    f"Field change was not propagated to DB2 downstream."
                )
                d = HypothesisDecision(
                    next_hypothesis="H2: Splunk confirms missed CDC events",
                    tools_to_call=[],
                    reasoning=root + note,
                    terminate=True,
                    root_cause=root,
                    confidence=0.84,
                )
                return {
                    "current_hypothesis": d.next_hypothesis,
                    "hypotheses_tested": tested,
                    "root_cause": d.root_cause,
                    "confidence": d.confidence,
                    "requires_human_review": (d.confidence or 1.0) < 0.75,
                    "tool_calls": [],
                    "iterations": iterations,
                }

        # ── H3: FLS + CDC + Apex fan-out ─────────────────────────────────────
        if "H3" not in tested:
            integration_user = row.get("sf_modified_by") or "sf-integration@org.com"
            HypothesisDecision(
                next_hypothesis="H3: FLS + CDC + Apex fan-out",
                tools_to_call=["get_field_permissions", "get_cdc_field_config", "get_apex_trigger_config"],
                reasoning=f"H2 inconclusive. Running FLS/CDC/Apex checks.{note}",
                terminate=False,
            )
            return {
                "current_hypothesis": "H3: FLS + CDC + Apex fan-out",
                "hypotheses_tested": tested + ["H3"],
                "tool_calls": [
                    {
                        "tool": "get_field_permissions",
                        "args": {
                            "integration_user": integration_user,
                            "sf_object": row["sf_object"],
                            "sf_field": row["sf_field"],
                        },
                        "hypothesis_key": "H3",
                    },
                    {
                        "tool": "get_cdc_field_config",
                        "args": {
                            "sf_object": row["sf_object"],
                            "sf_field": row["sf_field"],
                        },
                        "hypothesis_key": "H3",
                    },
                    {
                        "tool": "get_apex_trigger_config",
                        "args": {"sf_object": row["sf_object"]},
                        "hypothesis_key": "H3",
                    },
                ],
                "iterations": iterations,
            }

        # Evaluate H3
        h3 = [e for e in evidence if e.get("hypothesis_key") == "H3"]
        root_cause, confidence = self._analyze_h3(h3, row)
        if root_cause:
            d = HypothesisDecision(
                next_hypothesis="H3: Root cause confirmed",
                tools_to_call=[],
                reasoning=root_cause + note,
                terminate=True,
                root_cause=root_cause,
                confidence=confidence,
            )
            return {
                "current_hypothesis": d.next_hypothesis,
                "root_cause": root_cause,
                "confidence": confidence,
                "requires_human_review": (confidence or 1.0) < 0.75,
                "tool_calls": [],
                "iterations": iterations,
            }

        # H1–H3 exhausted → H5 RAG stub (Slice 4)
        HypothesisDecision(
            next_hypothesis="H5: RAG lookup required",
            tools_to_call=[],
            reasoning=f"H1/H2/H3 inconclusive. RAG context search needed (Slice 4).{note}",
            terminate=True,
        )
        return {
            "current_hypothesis": "H5: RAG lookup required (stub — Slice 4)",
            "hypotheses_ruled_out": state["hypotheses_ruled_out"] + ["H1", "H2", "H3"],
            "requires_human_review": True,
            "root_cause": None,
            "confidence": None,
            "tool_calls": [],
            "iterations": iterations,
        }

    def _value_mismatch(self, state: ReconState, iterations: int, note: str) -> dict:
        tested = state["hypotheses_tested"]
        evidence = state["evidence_collected"]
        row = state["recon_row"]
        integration_user = row.get("sf_modified_by") or "sf-integration@org.com"

        # HVM1: Splunk — DataWeave transform errors
        if "HVM1" not in tested:
            return {
                "current_hypothesis": "HVM1: DataWeave transform error in middleware",
                "hypotheses_tested": tested + ["HVM1"],
                "tool_calls": [{"tool": "splunk_stub", "args": {
                    "sf_record_id": row["sf_record_id"],
                    "sf_field": row["sf_field"],
                    "sf_object": row["sf_object"],
                }, "hypothesis_key": "HVM1"}],
                "iterations": iterations,
            }

        # HVM2: FLS permissions causing wrong value reads
        if "HVM2" not in tested:
            return {
                "current_hypothesis": "HVM2: FLS permission restricting field read",
                "hypotheses_tested": tested + ["HVM2"],
                "tool_calls": [{"tool": "get_field_permissions", "args": {
                    "integration_user": integration_user,
                    "sf_object": row["sf_object"],
                    "sf_field": row["sf_field"],
                }, "hypothesis_key": "HVM2"}],
                "iterations": iterations,
            }

        # HVM3: CDC channel config — field transformation or exclusion
        if "HVM3" not in tested:
            return {
                "current_hypothesis": "HVM3: CDC channel config or Apex conditional publish",
                "hypotheses_tested": tested + ["HVM3"],
                "tool_calls": [
                    {"tool": "get_cdc_field_config", "args": {
                        "sf_object": row["sf_object"], "sf_field": row["sf_field"],
                    }, "hypothesis_key": "HVM3"},
                    {"tool": "get_apex_trigger_config", "args": {
                        "sf_object": row["sf_object"],
                    }, "hypothesis_key": "HVM3"},
                ],
                "iterations": iterations,
            }

        # Evaluate HVM2 FLS
        hvm2 = next((e for e in evidence if e.get("hypothesis_key") == "HVM2"), None)
        if hvm2 and not hvm2.get("result", {}).get("has_read_access"):
            r = hvm2["result"]
            psets = ", ".join(r.get("permission_sets") or []) or "none assigned"
            root = (
                f"Integration user '{r.get('integration_user')}' lacks FLS read access to "
                f"{row['sf_object']}.{row['sf_field']}. Permission sets: {psets}. "
                f"Partial or default value being written to DB2."
            )
            return {
                "current_hypothesis": "HVM2: FLS gap confirmed",
                "root_cause": root, "confidence": 0.85,
                "requires_human_review": False,
                "tool_calls": [], "iterations": iterations,
            }

        # Evaluate HVM3 CDC/Apex
        hvm3 = [e for e in evidence if e.get("hypothesis_key") == "HVM3"]
        root_cause, confidence = self._analyze_h3(hvm3, row)
        if root_cause:
            return {
                "current_hypothesis": "HVM3: CDC/Apex root cause confirmed",
                "root_cause": root_cause, "confidence": confidence,
                "requires_human_review": (confidence or 1.0) < 0.75,
                "tool_calls": [], "iterations": iterations,
            }

        # HVM1–3 inconclusive — route to RAG
        return {
            "current_hypothesis": "HVM exhausted — RAG lookup needed",
            "hypotheses_ruled_out": tested,
            "requires_human_review": True,
            "root_cause": None, "confidence": None,
            "tool_calls": [], "iterations": iterations,
        }

    def _stale_value(self, state: ReconState, iterations: int, note: str) -> dict:
        tested = state["hypotheses_tested"]
        evidence = state["evidence_collected"]
        row = state["recon_row"]

        # HSV1: Check DB2 field history for stale timestamp
        if "HSV1" not in tested:
            return {
                "current_hypothesis": "HSV1: DB2 field history — stale timestamp check",
                "hypotheses_tested": tested + ["HSV1"],
                "tool_calls": [{"tool": "query_db2_field_history", "args": {
                    "sf_object": row["sf_object"],
                    "sf_field": row["sf_field"],
                    "sf_record_id": row["sf_record_id"],
                }, "hypothesis_key": "HSV1"}],
                "iterations": iterations,
            }

        # HSV2: CDC config — field excluded or TTL cache issue
        if "HSV2" not in tested:
            return {
                "current_hypothesis": "HSV2: CDC channel config or middleware cache TTL",
                "hypotheses_tested": tested + ["HSV2"],
                "tool_calls": [{"tool": "get_cdc_field_config", "args": {
                    "sf_object": row["sf_object"], "sf_field": row["sf_field"],
                }, "hypothesis_key": "HSV2"}],
                "iterations": iterations,
            }

        # Evaluate HSV2
        hsv2 = next((e for e in evidence if e.get("hypothesis_key") == "HSV2"), None)
        if hsv2 and not hsv2.get("result", {}).get("is_tracked"):
            r = hsv2["result"]
            root = (
                f"Field '{row['sf_field']}' is excluded from CDC tracking "
                f"(channel: {r.get('cdc_channel') or 'unknown'}). "
                f"DB2 retains the last synced value and does not receive updates."
            )
            return {
                "current_hypothesis": "HSV2: CDC exclusion confirmed",
                "root_cause": root, "confidence": 0.87,
                "requires_human_review": False,
                "tool_calls": [], "iterations": iterations,
            }

        return {
            "current_hypothesis": "HSV exhausted — RAG lookup needed",
            "hypotheses_ruled_out": tested,
            "requires_human_review": True,
            "root_cause": None, "confidence": None,
            "tool_calls": [], "iterations": iterations,
        }

    def _missing_record(self, state: ReconState, iterations: int, note: str) -> dict:
        tested = state["hypotheses_tested"]
        evidence = state["evidence_collected"]
        row = state["recon_row"]
        integration_user = row.get("sf_modified_by") or "sf-integration@org.com"

        # HMR1: DB2 field history — was record ever written?
        if "HMR1" not in tested:
            return {
                "current_hypothesis": "HMR1: DB2 history — record ever written?",
                "hypotheses_tested": tested + ["HMR1"],
                "tool_calls": [{"tool": "query_db2_field_history", "args": {
                    "sf_object": row["sf_object"],
                    "sf_field": row["sf_field"],
                    "sf_record_id": row["sf_record_id"],
                }, "hypothesis_key": "HMR1"}],
                "iterations": iterations,
            }

        # HMR2: Apex routing — record silently dropped by trigger
        if "HMR2" not in tested:
            return {
                "current_hypothesis": "HMR2: Apex routing — record silently dropped",
                "hypotheses_tested": tested + ["HMR2"],
                "tool_calls": [
                    {"tool": "get_apex_trigger_config", "args": {
                        "sf_object": row["sf_object"],
                    }, "hypothesis_key": "HMR2"},
                    {"tool": "get_field_permissions", "args": {
                        "integration_user": integration_user,
                        "sf_object": row["sf_object"],
                        "sf_field": row["sf_field"],
                    }, "hypothesis_key": "HMR2"},
                ],
                "iterations": iterations,
            }

        # Evaluate HMR1 — never written → routing/FLS issue
        hmr1 = next((e for e in evidence if e.get("hypothesis_key") == "HMR1"), None)
        if hmr1 and not hmr1.get("result", {}).get("was_populated"):
            root = (
                f"No historical value found in DB2 for {row['sf_object']}.{row['sf_field']} "
                f"(record {row['sf_record_id']}). Record was likely silently dropped by a "
                f"middleware routing rule or Apex trigger before reaching the DB2 write operation."
            )
            return {
                "current_hypothesis": "HMR1: Record never written — routing failure",
                "root_cause": root, "confidence": 0.80,
                "requires_human_review": False,
                "tool_calls": [], "iterations": iterations,
            }

        return {
            "current_hypothesis": "HMR exhausted — RAG lookup needed",
            "hypotheses_ruled_out": tested,
            "requires_human_review": True,
            "root_cause": None, "confidence": None,
            "tool_calls": [], "iterations": iterations,
        }

    def _duplicate_downstream(self, state: ReconState, iterations: int, note: str) -> dict:
        tested = state["hypotheses_tested"]
        evidence = state["evidence_collected"]
        row = state["recon_row"]

        # HDD1: Splunk — retry storm producing duplicate inserts
        if "HDD1" not in tested:
            return {
                "current_hypothesis": "HDD1: Splunk — retry storm / duplicate insert events",
                "hypotheses_tested": tested + ["HDD1"],
                "tool_calls": [{"tool": "splunk_stub", "args": {
                    "sf_record_id": row["sf_record_id"],
                    "sf_field": row["sf_field"],
                    "sf_object": row["sf_object"],
                }, "hypothesis_key": "HDD1"}],
                "iterations": iterations,
            }

        # HDD2: DB2 history — idempotency key check
        if "HDD2" not in tested:
            return {
                "current_hypothesis": "HDD2: DB2 upsert idempotency — missing MERGE key",
                "hypotheses_tested": tested + ["HDD2"],
                "tool_calls": [{"tool": "query_db2_field_history", "args": {
                    "sf_object": row["sf_object"],
                    "sf_field": row["sf_field"],
                    "sf_record_id": row["sf_record_id"],
                }, "hypothesis_key": "HDD2"}],
                "iterations": iterations,
            }

        # Evaluate HDD1
        hdd1 = next((e for e in evidence if e.get("hypothesis_key") == "HDD1"), None)
        if hdd1 and hdd1.get("result", {}).get("missed_events"):
            r = hdd1["result"]
            root = (
                f"Splunk detected {r.get('missed_count', 0)} retry events for "
                f"record {row['sf_record_id']}. Missing idempotency key (MERGE on SalesforceId) "
                f"in the {row.get('integration_name') or 'integration'} DB2 upsert logic "
                f"caused INSERT instead of MERGE on retry, producing duplicates."
            )
            return {
                "current_hypothesis": "HDD1: Retry-induced duplicate confirmed",
                "root_cause": root, "confidence": 0.83,
                "requires_human_review": False,
                "tool_calls": [], "iterations": iterations,
            }

        return {
            "current_hypothesis": "HDD exhausted — RAG lookup needed",
            "hypotheses_ruled_out": tested,
            "requires_human_review": True,
            "root_cause": None, "confidence": None,
            "tool_calls": [], "iterations": iterations,
        }

    def _analyze_h3(
        self, h3_ev: list[dict], row: dict
    ) -> tuple[str | None, float | None]:
        fls = next((e for e in h3_ev if e.get("tool") == "get_field_permissions"), None)
        cdc = next((e for e in h3_ev if e.get("tool") == "get_cdc_field_config"), None)
        apex = next((e for e in h3_ev if e.get("tool") == "get_apex_trigger_config"), None)

        if fls and not fls.get("result", {}).get("has_read_access"):
            r = fls["result"]
            psets = ", ".join(r.get("permission_sets") or []) or "none assigned"
            return (
                f"Integration user '{r.get('integration_user')}' lacks FLS read access to "
                f"{row['sf_object']}.{row['sf_field']} ({r.get('api_name')}). "
                f"Permission sets: {psets}.",
                0.88,
            )

        if cdc and not cdc.get("result", {}).get("is_tracked"):
            r = cdc["result"]
            return (
                f"Field '{row['sf_field']}' is excluded from CDC tracking "
                f"(channel: {r.get('cdc_channel') or 'unknown'}, "
                f"reason: {r.get('reason_excluded') or 'unknown'}). "
                f"Changes will not propagate downstream.",
                0.85,
            )

        if apex and apex.get("result", {}).get("has_conditional_publish"):
            r = apex["result"]
            return (
                f"Apex trigger '{r.get('trigger_name')}' on {row['sf_object']} has "
                f"conditional publish logic that may suppress null values: "
                f"{r.get('conditional_logic_description') or 'undocumented condition'}.",
                0.72,  # intentionally < 0.75 → requires_human_review
            )

        return None, None
