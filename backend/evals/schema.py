"""Schema for eval results files (validated on write and in tests)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class Rate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    k: int
    n: int
    rate: Optional[float]
    ci95: Optional[tuple[float, float]]


class Accuracy(BaseModel):
    overall: Rate
    by_discrepancy_type: dict[str, Rate]
    confusion: dict[str, dict[str, int]]


class Routing(BaseModel):
    unsafe_auto_clear: Rate
    review_rate: Rate
    review_vs_label: dict
    calibration_graph_confidence: dict
    calibration_final_confidence: dict


class Metrics(BaseModel):
    errors: dict
    accuracy: Accuracy
    efficiency: dict[str, Optional[Rate | float]]
    routing: Routing
    explanation: dict
    consistency: Optional[dict[str, Rate]]
    retrieval: dict
    cost_latency: dict[str, Optional[float]]


class Dataset(BaseModel):
    path: str
    sha256: str
    scenarios_sha256: str
    incidents: int


class IncidentRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    run: int
    discrepancy_type: str
    label: dict
    error: Optional[str]
    correct: bool
    requires_review: bool


class EvalResults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    mode: Literal["offline", "live"]
    config: Literal["claude", "groq", "hybrid"]
    models: list[str]
    runs: int
    created_at: str
    git_sha: Optional[str]
    dataset: Dataset
    graph_version: str
    prompt_versions: dict[str, str]
    pricing_per_mtok: dict[str, list[float]]
    caveats: list[str]
    environment_notes: list[str]
    metrics: Metrics
    critic_planted: dict
    ablations: Optional[dict[str, dict]]
    failure_patterns: list[dict]
    incidents: list[IncidentRecord]
