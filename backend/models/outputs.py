from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from backend.models.entities import (
    DiscrepancyType,
    EvidenceSourceType,
    ReconRow,
    Severity,
)


class ClassifiedReconRow(ReconRow):
    discrepancy_type: DiscrepancyType
    severity: Severity
    deployment_correlated: bool = False


class HypothesisDecision(BaseModel):
    next_hypothesis: str
    tools_to_call: list[str]
    reasoning: str
    terminate: bool
    root_cause: str | None = None
    confidence: float | None = None


class EvidenceResult(BaseModel):
    hypothesis_tested: str
    source_type: EvidenceSourceType
    source_reference: str
    content: str
    relevance_explanation: str
    rules_out: list[str]
    confirms: str | None = None


class RCAOutput(BaseModel):
    root_cause: str
    confidence: float
    evidence_ids: list[UUID]
    similar_past_incidents: list[UUID]
    suggested_fix: str
    postmortem_draft: str
    jira_summary: str
    requires_human_review: bool
