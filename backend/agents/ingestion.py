from __future__ import annotations

import time
from datetime import timedelta

from backend.config import AgentConfig
from backend.models.entities import DiscrepancyType, ReconRow, Severity
from backend.models.outputs import ClassifiedReconRow
from backend.models.state import ReconState

_CORE_FSC_OBJECTS = frozenset([
    "Contact", "Account", "FinancialAccount__c",
    "FinancialHolding__c", "Lead", "Opportunity",
])
_STALE_DAYS = 30
_DEPLOY_WINDOW_HOURS = 24


class IngestionAgent:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._llm = None  # lazy — only initialised on ambiguous rows

    @property
    def _get_llm(self):
        if self._llm is None:
            from langchain_anthropic import ChatAnthropic
            self._llm = ChatAnthropic(model=self._config.ingestion_llm)
        return self._llm

    def run(self, state: ReconState) -> dict:
        row_dict = state["recon_row"]
        db2_env = row_dict.get("db2_environment", "PROD")
        row = ReconRow.model_validate(row_dict)

        llm_calls: list[dict] = []

        discrepancy_type = row.discrepancy_type
        if discrepancy_type is None:
            discrepancy_type, llm_call = self._derive_discrepancy(row)
            if llm_call:
                llm_calls.append(llm_call)

        severity = row.severity
        if severity is None:
            severity = self._derive_severity(row, discrepancy_type, db2_env)

        deployment_correlated = self._deployment_correlated(row)

        row_data = row.model_dump()
        row_data.update({
            "discrepancy_type": discrepancy_type,
            "severity": severity,
            "deployment_correlated": deployment_correlated,
        })
        classified = ClassifiedReconRow.model_validate(row_data)

        return {
            "recon_row": {**classified.model_dump(mode="json"), "db2_environment": db2_env},
            "current_hypothesis": "",
            "hypotheses_tested": [],
            "hypotheses_ruled_out": [],
            "evidence_collected": [],
            "rag_candidates": [],
            "reranked_candidates": [],
            "root_cause": None,
            "confidence": None,
            "rca_output": None,
            "iterations": 0,
            "requires_human_review": False,
            "llm_calls": llm_calls,
            "tool_calls": [],
            "total_latency_ms": 0,
        }

    def _derive_discrepancy(
        self, row: ReconRow
    ) -> tuple[DiscrepancyType, dict | None]:
        sf = row.sf_value
        db2 = row.db2_value

        if sf is not None and not (db2 or "").strip():
            return DiscrepancyType.NULL_DOWNSTREAM, None

        if sf is not None and db2 is not None and sf.strip() != db2.strip():
            if row.sf_last_modified and row.db2_last_updated:
                if (row.sf_last_modified - row.db2_last_updated).days > _STALE_DAYS:
                    return DiscrepancyType.STALE_VALUE, None
            return DiscrepancyType.VALUE_MISMATCH, None

        # Ambiguous (both null, or values identical) — use Haiku
        return self._llm_classify(row)

    def _llm_classify(self, row: ReconRow) -> tuple[DiscrepancyType, dict]:
        from langchain_core.messages import HumanMessage

        start = time.time()
        prompt = (
            f"Classify this Salesforce-to-DB2 recon discrepancy.\n"
            f"SF Object: {row.sf_object}, Field: {row.sf_field}\n"
            f"SF Value: {row.sf_value!r}, DB2 Value: {row.db2_value!r}\n"
            f"SF Last Modified: {row.sf_last_modified}, "
            f"DB2 Last Updated: {row.db2_last_updated}\n"
            f"Integration: {row.integration_name}\n\n"
            f"Reply with exactly one of: NULL_DOWNSTREAM | MISSING_RECORD | "
            f"VALUE_MISMATCH | DUPLICATE_DOWNSTREAM | STALE_VALUE"
        )
        response = self._get_llm.invoke([HumanMessage(content=prompt)])
        latency_ms = int((time.time() - start) * 1000)

        usage = getattr(response, "usage_metadata", {}) or {}
        log = {
            "model": self._config.ingestion_llm,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "latency_ms": latency_ms,
            "purpose": "ambiguous_classification",
        }
        raw = response.content.strip().upper().split()[0]
        try:
            return DiscrepancyType(raw), log
        except ValueError:
            return DiscrepancyType.VALUE_MISMATCH, log

    def _derive_severity(
        self, row: ReconRow, dt: DiscrepancyType, db2_env: str
    ) -> Severity:
        prod = db2_env == "PROD"
        core = row.sf_object in _CORE_FSC_OBJECTS
        if prod and core and dt == DiscrepancyType.NULL_DOWNSTREAM:
            return Severity.P1
        if (prod and not core) or (not prod and core):
            return Severity.P2
        return Severity.P3

    def _deployment_correlated(self, row: ReconRow) -> bool:
        if not row.last_deployed_at or not row.sf_last_modified:
            return False
        delta = row.sf_last_modified - row.last_deployed_at
        return timedelta(0) <= delta <= timedelta(hours=_DEPLOY_WINDOW_HOURS)
