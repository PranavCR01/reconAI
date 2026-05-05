from __future__ import annotations

from backend.models.entities import (
    Evidence,
    RCAIncident,
    ReconArtifact,
    ReconRow,
    ReconRun,
    Resolution,
)
from backend.storage.adapter import StorageAdapter


class SalesforceAdapter(StorageAdapter):
    """Salesforce write-back adapter — stub. Implemented in a future slice."""

    def _ni(self, method: str) -> None:
        raise NotImplementedError(f"SalesforceAdapter.{method} is not yet implemented")

    async def save_recon_run(self, run: ReconRun) -> str:
        self._ni("save_recon_run")

    async def get_recon_run(self, run_id: str) -> ReconRun:
        self._ni("get_recon_run")

    async def save_recon_row(self, row: ReconRow) -> str:
        self._ni("save_recon_row")

    async def save_recon_rows(self, rows: list[ReconRow]) -> list[str]:
        self._ni("save_recon_rows")

    async def save_rca_incident(self, incident: RCAIncident) -> str:
        self._ni("save_rca_incident")

    async def save_evidence(self, evidence: Evidence) -> str:
        self._ni("save_evidence")

    async def save_resolution(self, resolution: Resolution) -> str:
        self._ni("save_resolution")

    async def get_incidents_for_run(self, run_id: str) -> list[RCAIncident]:
        self._ni("get_incidents_for_run")

    async def get_recon_rows_for_run(self, run_id: str) -> list[ReconRow]:
        self._ni("get_recon_rows_for_run")

    async def save_artifact(self, artifact: ReconArtifact, embedding: list[float] | None = None) -> str:
        self._ni("save_artifact")

    async def get_artifact(self, artifact_id: str) -> ReconArtifact:
        self._ni("get_artifact")

    async def search_similar_artifacts(self, embedding: list[float], limit: int = 5) -> list[ReconArtifact]:
        self._ni("search_similar_artifacts")

    async def get_incident_by_id(self, incident_id: str) -> RCAIncident:
        self._ni("get_incident_by_id")

    async def get_evidence_for_incident(self, incident_id: str) -> list[Evidence]:
        self._ni("get_evidence_for_incident")

    async def check_cache(self, cache_key: str) -> dict | None:
        self._ni("check_cache")

    async def write_cache(self, cache_key: str, rca_output: dict, llm_model: str) -> None:
        self._ni("write_cache")

    async def update_recon_row_embedding(self, row_id: str, embedding: list[float]) -> None:
        self._ni("update_recon_row_embedding")
