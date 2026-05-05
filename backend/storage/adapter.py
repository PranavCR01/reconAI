from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models.entities import (
    Evidence,
    RCAIncident,
    ReconArtifact,
    ReconRow,
    ReconRun,
    Resolution,
)


class StorageAdapter(ABC):
    @abstractmethod
    async def save_recon_run(self, run: ReconRun) -> str: ...

    @abstractmethod
    async def get_recon_run(self, run_id: str) -> ReconRun: ...

    @abstractmethod
    async def save_recon_row(self, row: ReconRow) -> str: ...

    @abstractmethod
    async def save_recon_rows(self, rows: list[ReconRow]) -> list[str]: ...

    @abstractmethod
    async def save_rca_incident(self, incident: RCAIncident) -> str: ...

    @abstractmethod
    async def save_evidence(self, evidence: Evidence) -> str: ...

    @abstractmethod
    async def save_resolution(self, resolution: Resolution) -> str: ...

    @abstractmethod
    async def get_incidents_for_run(self, run_id: str) -> list[RCAIncident]: ...

    @abstractmethod
    async def get_recon_rows_for_run(self, run_id: str) -> list[ReconRow]: ...

    @abstractmethod
    async def save_artifact(self, artifact: ReconArtifact, embedding: list[float] | None = None) -> str: ...

    @abstractmethod
    async def get_artifact(self, artifact_id: str) -> ReconArtifact: ...

    @abstractmethod
    async def search_similar_artifacts(self, embedding: list[float], limit: int = 5) -> list[ReconArtifact]: ...

    @abstractmethod
    async def get_incident_by_id(self, incident_id: str) -> RCAIncident: ...

    @abstractmethod
    async def get_evidence_for_incident(self, incident_id: str) -> list[Evidence]: ...

    @abstractmethod
    async def check_cache(self, cache_key: str) -> dict | None: ...

    @abstractmethod
    async def write_cache(self, cache_key: str, rca_output: dict, llm_model: str) -> None: ...

    @abstractmethod
    async def update_recon_row_embedding(self, row_id: str, embedding: list[float]) -> None: ...
