from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from supabase import Client, create_client

from backend.models.entities import (
    Evidence,
    RCAIncident,
    ReconArtifact,
    ReconRow,
    ReconRun,
    Resolution,
)
from backend.storage.adapter import StorageAdapter


def _dump(model: Any) -> dict:
    return model.model_dump(mode="json", exclude_none=True)


class SupabaseAdapter(StorageAdapter):
    def __init__(self, client: Client) -> None:
        self._client = client

    @classmethod
    def from_env(cls) -> SupabaseAdapter:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        return cls(create_client(url, key))

    async def _run(self, fn):
        return await asyncio.to_thread(fn)

    async def save_recon_run(self, run: ReconRun) -> str:
        result = await self._run(
            lambda: self._client.table("recon_runs").insert(_dump(run)).execute()
        )
        return result.data[0]["id"]

    async def get_recon_run(self, run_id: str) -> ReconRun:
        result = await self._run(
            lambda: self._client.table("recon_runs")
            .select("*")
            .eq("id", run_id)
            .single()
            .execute()
        )
        return ReconRun.model_validate(result.data)

    async def save_recon_row(self, row: ReconRow) -> str:
        result = await self._run(
            lambda: self._client.table("recon_rows").insert(_dump(row)).execute()
        )
        return result.data[0]["id"]

    async def save_recon_rows(self, rows: list[ReconRow]) -> list[str]:
        if not rows:
            return []
        payload = [_dump(r) for r in rows]
        result = await self._run(
            lambda: self._client.table("recon_rows").insert(payload).execute()
        )
        return [r["id"] for r in result.data]

    async def save_rca_incident(self, incident: RCAIncident) -> str:
        result = await self._run(
            lambda: self._client.table("rca_incidents").insert(_dump(incident)).execute()
        )
        return result.data[0]["id"]

    async def save_evidence(self, evidence: Evidence) -> str:
        result = await self._run(
            lambda: self._client.table("rca_evidence").insert(_dump(evidence)).execute()
        )
        return result.data[0]["id"]

    async def save_resolution(self, resolution: Resolution) -> str:
        result = await self._run(
            lambda: self._client.table("resolutions")
            .upsert(_dump(resolution), on_conflict="incident_id")
            .execute()
        )
        return result.data[0]["id"]

    async def get_recon_rows_for_run(self, run_id: str) -> list[ReconRow]:
        result = await self._run(
            lambda: self._client.table("recon_rows")
            .select("*")
            .eq("run_id", run_id)
            .execute()
        )
        return [ReconRow.model_validate(r) for r in result.data]

    async def get_incidents_for_run(self, run_id: str) -> list[RCAIncident]:
        rows_result = await self._run(
            lambda: self._client.table("recon_rows")
            .select("id")
            .eq("run_id", run_id)
            .execute()
        )
        row_ids: set[str] = {r["id"] for r in rows_result.data}
        if not row_ids:
            return []
        result = await self._run(
            lambda: self._client.table("rca_incidents")
            .select("*")
            .in_("recon_row_id", list(row_ids))
            .execute()
        )
        # Python-level guard ensures cross-run incidents never leak through
        seen = {}
        for r in result.data:
            if r.get("recon_row_id") not in row_ids:
                continue
            row_id = r["recon_row_id"]
            if row_id not in seen or (r.get("created_at") or "") > (seen[row_id].get("created_at") or ""):
                seen[row_id] = r
        return [RCAIncident.model_validate(r) for r in seen.values()]

    async def get_incident_by_id(self, incident_id: str) -> RCAIncident:
        result = await self._run(
            lambda: self._client.table("rca_incidents")
            .select("*")
            .eq("id", incident_id)
            .single()
            .execute()
        )
        return RCAIncident.model_validate(result.data)

    async def get_evidence_for_incident(self, incident_id: str) -> list[Evidence]:
        result = await self._run(
            lambda: self._client.table("rca_evidence")
            .select("*")
            .eq("incident_id", incident_id)
            .execute()
        )
        return [Evidence.model_validate(r) for r in result.data]

    async def check_cache(self, cache_key: str) -> dict | None:
        result = await self._run(
            lambda: self._client.table("rca_cache")
            .select("rca_output,expires_at")
            .eq("cache_key", cache_key)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        expires_at = row.get("expires_at")
        if expires_at:
            try:
                if isinstance(expires_at, str):
                    exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                else:
                    exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
                if exp < datetime.now(timezone.utc):
                    return None
            except Exception:
                pass
        # llm_model is stored inside rca_output to avoid schema dependencies
        rca_output = row.get("rca_output") or {}
        return {
            "rca_output": rca_output,
            "llm_model": rca_output.get("_llm_model"),
        }

    async def write_cache(self, cache_key: str, rca_output: dict, llm_model: str) -> None:
        # llm_model stored inside rca_output under _llm_model to stay within original schema
        payload_rca = {**rca_output, "_llm_model": llm_model}
        payload = {
            "cache_key": cache_key,
            "rca_output": payload_rca,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        }
        await self._run(
            lambda: self._client.table("rca_cache")
            .upsert(payload)
            .execute()
        )

    async def update_recon_row_embedding(self, row_id: str, embedding: list[float]) -> None:
        await self._run(
            lambda: self._client.table("recon_rows")
            .update({"embedding": embedding})
            .eq("id", row_id)
            .execute()
        )

    async def update_run_status(self, run_id: str, status: str, completed_at: datetime) -> None:
        await self._run(
            lambda: self._client.table("recon_runs")
            .update({"status": status, "completed_at": completed_at.isoformat()})
            .eq("id", run_id)
            .execute()
        )

    async def save_artifact(self, artifact: ReconArtifact, embedding: list[float] | None = None) -> str:
        payload = _dump(artifact)
        if embedding is not None:
            payload["embedding"] = embedding
        result = await self._run(
            lambda: self._client.table("recon_artifacts").insert(payload).execute()
        )
        return result.data[0]["id"]

    async def get_artifact(self, artifact_id: str) -> ReconArtifact:
        result = await self._run(
            lambda: self._client.table("recon_artifacts")
            .select("*")
            .eq("id", artifact_id)
            .single()
            .execute()
        )
        return ReconArtifact.model_validate(result.data)

    async def search_similar_artifacts(self, embedding: list[float], limit: int = 5) -> list[ReconArtifact]:
        result = await self._run(
            lambda: self._client.rpc(
                "match_artifacts",
                {"query_embedding": embedding, "match_threshold": 0.4, "match_count": limit},
            ).execute()
        )
        return [ReconArtifact.model_validate(r) for r in result.data]

    def search_artifacts_sync(self, embedding: list[float], limit: int = 5) -> list[dict]:
        result = self._client.rpc(
            "match_artifacts",
            {"query_embedding": embedding, "match_threshold": 0.4, "match_count": limit},
        ).execute()
        return result.data

    # -----------------------------------------------------------------------
    # Analytics query methods (Slice 8)
    # -----------------------------------------------------------------------

    async def get_incidents_since(self, since: datetime, limit: int = 2000) -> list[dict]:
        result = await self._run(
            lambda: self._client.table("rca_incidents")
            .select("id,recon_row_id,created_at,confidence,status,requires_human_review,total_tokens_used,total_tool_calls,latency_ms")
            .gte("created_at", since.isoformat())
            .order("created_at")
            .limit(limit)
            .execute()
        )
        return result.data

    async def get_recon_rows_since(self, since: datetime, limit: int = 5000) -> list[dict]:
        """Fetch recon_rows by date range — avoids .in_() on large ID lists."""
        result = await self._run(
            lambda: self._client.table("recon_rows")
            .select("id,sf_object,sf_field,discrepancy_type,severity,run_id")
            .gte("created_at", since.isoformat())
            .limit(limit)
            .execute()
        )
        return result.data

    async def get_resolutions_since(self, since: datetime) -> list[dict]:
        result = await self._run(
            lambda: self._client.table("resolutions")
            .select("id,resolved_at,ai_was_correct,fix_type,incident_id")
            .gte("resolved_at", since.isoformat())
            .execute()
        )
        return result.data

    async def get_runs_since(self, since: datetime) -> list[dict]:
        result = await self._run(
            lambda: self._client.table("recon_runs")
            .select("id,created_at,status")
            .gte("created_at", since.isoformat())
            .execute()
        )
        return result.data

    async def get_total_runs_count(self) -> int:
        result = await self._run(
            lambda: self._client.table("recon_runs").select("id", count="exact").execute()
        )
        return result.count or 0

    async def get_deployment_events_since(self, since: datetime) -> list[dict]:
        result = await self._run(
            lambda: self._client.table("deployment_events")
            .select("*")
            .gte("deployed_at", since.isoformat())
            .order("deployed_at", desc=True)
            .execute()
        )
        return result.data

    async def get_all_deployment_events(self) -> list[dict]:
        result = await self._run(
            lambda: self._client.table("deployment_events")
            .select("*")
            .order("deployed_at", desc=True)
            .execute()
        )
        return result.data

    # -----------------------------------------------------------------------
    # Tracking methods
    # -----------------------------------------------------------------------

    async def get_resolution_for_incident(self, incident_id: str) -> Resolution | None:
        result = await self._run(
            lambda: self._client.table("resolutions")
            .select("*")
            .eq("incident_id", incident_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return Resolution.model_validate(result.data[0])

    async def insert_page_view(self, data: dict) -> None:
        await self._run(
            lambda: self._client.table("page_views").insert(data).execute()
        )

    async def insert_demo_request(self, data: dict) -> None:
        await self._run(
            lambda: self._client.table("demo_requests").insert(data).execute()
        )
