"""In-memory stand-in for supabase-py's Client.

Implements the PostgREST surface SupabaseAdapter and the seed scripts use, so tests
run the *real* adapter code: insert/upsert/update/delete, eq/neq/gte/in_/order/
limit/single, count="exact", DB defaults (id, created_at, resolved_at), and the
match_artifacts RPC (cosine similarity with threshold and limit).
"""
from __future__ import annotations

import copy
import math
import threading
import uuid
from datetime import datetime, timezone

# Columns Postgres fills on insert when the payload omits them.
DEFAULT_TIMESTAMP = {
    "recon_runs": "created_at",
    "recon_rows": "created_at",
    "rca_incidents": "created_at",
    "rca_evidence": "created_at",
    "resolutions": "resolved_at",
    "recon_artifacts": "created_at",
    "rca_cache": "created_at",
    "page_views": "created_at",
    "demo_requests": "requested_at",
    "deployment_events": "created_at",
}
PRIMARY_KEY = {"rca_cache": "cache_key"}


class APIError(Exception):
    """Mirrors postgrest.exceptions.APIError closely enough for adapter callers."""


class _Response:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _comparable(value):
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value


class _Query:
    def __init__(self, db: "FakeSupabase", table: str):
        self._db = db
        self._table = table
        self._op = "select"
        self._payload = None
        self._filters: list[tuple[str, str, object]] = []
        self._single = False
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._count: str | None = None
        self._on_conflict: str | None = None

    # -- builders ---------------------------------------------------------
    def select(self, columns="*", count=None):
        self._op, self._count = "select", count
        return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def upsert(self, payload, on_conflict=None):
        self._op, self._payload, self._on_conflict = "upsert", payload, on_conflict
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, column, value):
        self._filters.append(("eq", column, value))
        return self

    def neq(self, column, value):
        self._filters.append(("neq", column, value))
        return self

    def gte(self, column, value):
        self._filters.append(("gte", column, value))
        return self

    def in_(self, column, values):
        self._filters.append(("in", column, list(values)))
        return self

    def order(self, column, desc=False):
        self._order = (column, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def single(self):
        self._single = True
        return self

    # -- execution --------------------------------------------------------
    def _matches(self, row: dict) -> bool:
        for op, column, value in self._filters:
            current = row.get(column)
            if op == "eq" and str(current) != str(value):
                return False
            if op == "neq" and str(current) == str(value):
                return False
            if op == "in" and str(current) not in {str(v) for v in value}:
                return False
            if op == "gte" and (current is None or _comparable(current) < _comparable(value)):
                return False
        return True

    def _with_defaults(self, row: dict) -> dict:
        row = copy.deepcopy(row)
        if self._table not in PRIMARY_KEY:
            row.setdefault("id", str(uuid.uuid4()))
        ts_column = DEFAULT_TIMESTAMP.get(self._table)
        if ts_column:
            row.setdefault(ts_column, _now())
        return row

    def execute(self) -> _Response:
        db = self._db
        with db.lock:
            db.calls.append((self._table, self._op))
            if db.fail_tables.get(self._table):
                raise APIError(f"injected failure on {self._table}")
            rows = db.tables.setdefault(self._table, [])

            if self._op in ("insert", "upsert"):
                items = self._payload if isinstance(self._payload, list) else [self._payload]
                out = []
                for item in items:
                    new = self._with_defaults(item)
                    key = self._on_conflict or PRIMARY_KEY.get(self._table) or ("id" if self._op == "upsert" else None)
                    if self._op == "upsert" and key:
                        existing = next((r for r in rows if str(r.get(key)) == str(new.get(key))), None)
                        if existing is not None:
                            keep_id = existing.get("id")
                            existing.update(new)
                            if keep_id is not None:
                                existing["id"] = keep_id
                            out.append(copy.deepcopy(existing))
                            continue
                    rows.append(new)
                    out.append(copy.deepcopy(new))
                return _Response(out)

            matched = [r for r in rows if self._matches(r)]
            if self._op == "update":
                for r in matched:
                    r.update(copy.deepcopy(self._payload))
                return _Response(copy.deepcopy(matched))
            if self._op == "delete":
                db.tables[self._table] = [r for r in rows if r not in matched]
                return _Response(copy.deepcopy(matched))

            result = copy.deepcopy(matched)
            if self._order:
                column, desc = self._order
                result.sort(key=lambda r: (r.get(column) is None, str(_comparable(r.get(column)))), reverse=desc)
            count = len(result) if self._count == "exact" else None
            if self._limit is not None:
                result = result[: self._limit]
            if self._single:
                if len(result) != 1:
                    raise APIError(f"JSON object requested, multiple (or no) rows returned ({len(result)})")
                return _Response(result[0], count)
            return _Response(result, count)


class _Rpc:
    def __init__(self, db: "FakeSupabase", name: str, params: dict):
        self._db, self._name, self._params = db, name, params

    def execute(self) -> _Response:
        db = self._db
        with db.lock:
            db.calls.append(("rpc", self._name))
            if db.fail_tables.get("rpc:" + self._name):
                raise APIError(f"injected failure on rpc {self._name}")
            if self._name != "match_artifacts":
                raise APIError(f"unknown rpc {self._name}")
            query = self._params["query_embedding"]
            scored = []
            for artifact in db.tables.get("recon_artifacts", []):
                emb = artifact.get("embedding")
                if not emb:
                    continue
                sim = cosine(query, emb)
                if sim >= self._params["match_threshold"]:
                    row = {k: v for k, v in artifact.items() if k != "embedding"}
                    row["similarity"] = sim
                    scored.append(row)
            scored.sort(key=lambda r: -r["similarity"])
            return _Response(scored[: self._params["match_count"]])


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class FakeSupabase:
    """One isolated in-memory database. `create_client` hands out this instance."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self.calls: list[tuple[str, str]] = []
        self.fail_tables: dict[str, bool] = {}
        self.lock = threading.RLock()

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def rpc(self, name: str, params: dict) -> _Rpc:
        return _Rpc(self, name, params)

    def rows(self, table: str) -> list[dict]:
        return copy.deepcopy(self.tables.get(table, []))
