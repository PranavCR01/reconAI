from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from backend.models.entities import ReconRow

_TTL_DAYS = 30


def make_cache_key(row: ReconRow) -> str:
    parts = "|".join([
        str(row.discrepancy_type.value) if row.discrepancy_type else "",
        row.sf_object or "",
        row.sf_field or "",
        row.integration_name or "",
    ])
    return hashlib.sha256(parts.encode()).hexdigest()


async def check_cache(storage, key: str) -> dict | None:
    try:
        return await storage.check_cache(key)
    except Exception:
        return None


async def write_cache(storage, key: str, rca_output: dict, llm_model: str) -> None:
    try:
        await storage.write_cache(key, rca_output, llm_model)
    except Exception:
        pass
