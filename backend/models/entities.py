from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DiscrepancyType(str, Enum):
    NULL_DOWNSTREAM = "NULL_DOWNSTREAM"
    MISSING_RECORD = "MISSING_RECORD"
    VALUE_MISMATCH = "VALUE_MISMATCH"
    DUPLICATE_DOWNSTREAM = "DUPLICATE_DOWNSTREAM"
    STALE_VALUE = "STALE_VALUE"


class Severity(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class EvidenceSourceType(str, Enum):
    splunk_log = "splunk_log"
    sf_field_history = "sf_field_history"
    sf_field_permissions = "sf_field_permissions"
    apex_job_log = "apex_job_log"
    platform_event_usage = "platform_event_usage"
    middleware_log = "middleware_log"
    code_chunk = "code_chunk"
    past_incident = "past_incident"


class FixType(str, Enum):
    apex_code_change = "apex_code_change"
    dataweave_mapping_fix = "dataweave_mapping_fix"
    fls_permission_grant = "fls_permission_grant"
    cdc_channel_config = "cdc_channel_config"
    replay_manual_trigger = "replay_manual_trigger"
    middleware_restart = "middleware_restart"
    data_backfill = "data_backfill"
    other = "other"


class IncidentStatus(str, Enum):
    running = "running"
    complete = "complete"
    needs_review = "needs_review"
    escalated = "escalated"


class ReconRun(BaseModel):
    id: Optional[UUID] = None
    run_date: date
    triggered_by: str = "manual"
    sf_org_id: str
    db2_environment: str
    total_rows_checked: int = 0
    total_discrepancies: int = 0
    status: str = "pending"
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ReconRow(BaseModel):
    id: Optional[UUID] = None
    run_id: Optional[UUID] = None
    sf_object: str
    sf_field: str
    sf_record_id: str
    sf_value: Optional[str] = None
    sf_last_modified: Optional[datetime] = None
    sf_modified_by: Optional[str] = None
    db2_table: str
    db2_column: str
    db2_value: Optional[str] = None
    db2_last_updated: Optional[datetime] = None
    last_deployed_at: Optional[datetime] = None
    integration_name: Optional[str] = None
    discrepancy_type: Optional[DiscrepancyType] = None
    severity: Optional[Severity] = None
    created_at: Optional[datetime] = None


class RCAIncident(BaseModel):
    id: Optional[UUID] = None
    recon_row_id: Optional[UUID] = None
    hypotheses_tested: list[str] = Field(default_factory=list)
    hypotheses_ruled_out: list[str] = Field(default_factory=list)
    final_hypothesis: Optional[str] = None
    confidence: Optional[float] = None
    similar_incidents: list[UUID] = Field(default_factory=list)
    similarity_scores: list[float] = Field(default_factory=list)
    root_cause_summary: Optional[str] = None
    suggested_fix: Optional[str] = None
    postmortem_draft: Optional[str] = None
    jira_summary: Optional[str] = None
    requires_human_review: bool = False
    status: IncidentStatus = IncidentStatus.running
    llm_model: Optional[str] = None
    total_tool_calls: int = 0
    total_tokens_used: int = 0
    latency_ms: int = 0
    created_at: Optional[datetime] = None


class Evidence(BaseModel):
    id: Optional[UUID] = None
    incident_id: Optional[UUID] = None
    source_type: EvidenceSourceType
    source_reference: str
    content: str
    relevance_explanation: str
    created_at: Optional[datetime] = None


class Resolution(BaseModel):
    id: Optional[UUID] = None
    incident_id: Optional[UUID] = None
    confirmed_root_cause: str
    fix_applied: str
    fix_type: FixType
    fix_verified: bool = False
    verification_recon_run_id: Optional[UUID] = None
    ai_was_correct: Optional[bool] = None
    correction_notes: Optional[str] = None
    resolved_by: str
    resolved_at: Optional[datetime] = None


class ReconArtifact(BaseModel):
    id: Optional[UUID] = None
    artifact_type: str
    sf_object: Optional[str] = None
    sf_field: Optional[str] = None
    discrepancy_type: Optional[DiscrepancyType] = None
    root_cause_category: Optional[str] = None
    integration_name: Optional[str] = None
    resolution_confirmed: bool = False
    confidence_score: Optional[float] = None
    content: str
    source: Optional[str] = None
    created_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
