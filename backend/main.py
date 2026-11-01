from __future__ import annotations

import asyncio
import csv
import io
import json
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Optional

import os

import sentry_sdk
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.cache.rca_cache import check_cache, make_cache_key, write_cache
from backend.config import get_config, get_config_by_key, incident_cost
from backend.graph.recon_graph import build_graph
from backend.models.entities import (
    DiscrepancyType,
    Evidence,
    FixType,
    IncidentStatus,
    RCAIncident,
    ReconRow,
    ReconRun,
    Resolution,
    Severity,
)
from backend.models.state import initial_state, review_reasons
from backend.storage.supabase_adapter import SupabaseAdapter
from backend.tools.rag_tools import compute_recall_at_k, embed_text

load_dotenv()

_dsn = os.getenv("SENTRY_DSN", "")
if _dsn:
    sentry_sdk.init(dsn=_dsn, traces_sample_rate=0.1)

_storage: SupabaseAdapter | None = None
_recall_cache: dict = {"data": None, "ts": 0}
_RECALL_TTL = 3600  # 1 hour — recall@k is stable between artifact updates

_REQUIRED_CSV_COLUMNS = {"sf_object", "sf_field", "sf_record_id", "db2_table", "db2_column"}

_SEVERITY_ORDER = {Severity.P1: 0, Severity.P2: 1, Severity.P3: 2}

# Columns added by migrations in docs/sql/; checked at startup.
REQUIRED_COLUMNS: dict[str, list[str]] = {
    "rca_incidents": ["review_reasons", "llm_calls"],
    "rca_evidence": ["hypothesis_key", "tool", "tool_args", "outcome", "raw_result"],
}
REQUIRED_COLUMNS["rca_incidents"] += ["hypothesis_verdicts", "graph_status", "root_cause_category",
                                      "contributing_factors", "graph_version"]

_GRAPH_FIELDS = ("hypothesis_verdicts", "graph_status", "root_cause_category", "contributing_factors", "graph_version")
REQUIRED_COLUMNS["rca_incidents"] += ["claims", "judge_decision", "revision_count", "prompt_versions"]
REQUIRED_COLUMNS["rca_incidents"] += ["e2e_latency_ms", "cost_usd", "cost_warnings", "trace"]
REQUIRED_COLUMNS["rca_incidents"] += ["retrieval_error"]

# Review reasons that mean a dependency failed, not that the case is hard: never cache these.
_OUTAGE_REASONS = {"llm_unavailable", "critic_unavailable", "proposer_invalid_output", "missing_evidence"}


def degraded_because(final: dict, reasons: list[str]) -> list[str]:
    """Why a fresh result is degraded (empty = healthy). Degraded results are not cached, so the
    same rows are analyzed again once the dependency recovers."""
    why = sorted(set(reasons) & _OUTAGE_REASONS)
    if final.get("retrieval_error"):
        why.append("retrieval_error")
    if any(e.get("outcome") == "error" for e in final.get("evidence_collected") or []):
        why.append("tool_error")
    # Invalid output that a retry fixed is not an outage; an API error on any call is.
    if any(c.get("error") and not str(c["error"]).startswith("invalid output") for c in final.get("llm_calls") or []):
        why.append("llm_call_error")
    return sorted(set(why))


def _explanation_fields(rca: dict) -> dict:
    """Claims (with critic verdicts), judge decision, revisions and prompt versions from rca_output."""
    return {
        "claims": rca.get("claims") or [],
        "judge_decision": rca.get("judge_decision"),
        "revision_count": rca.get("revision_count") or 0,
        "prompt_versions": rca.get("prompt_versions") or {},
    }

# ---------------------------------------------------------------------------
# Cost guards — the app is public and every analyzed row costs LLM/embedding calls.
# In-memory: limits reset when the process restarts (fine for a single Render instance).
# ---------------------------------------------------------------------------
MAX_UPLOAD_ROWS = 200
MAX_UPLOAD_BYTES = 256 * 1024
UPLOADS_PER_IP_PER_HOUR = 20
UPLOADS_PER_DAY = 300            # all clients combined
ROWS_PER_DAY = 5000              # all clients combined — the real spend cap
BYPASS_CACHE_PER_IP_PER_HOUR = 5
BENCHMARKS_PER_IP_PER_HOUR = 3
_HOUR, _DAY = 3600, 86400

_rate_events: dict[str, deque] = defaultdict(deque)  # key -> deque[(timestamp, amount)]


def client_ip(headers, peer: str | None) -> str:
    """Client IP for rate limiting.

    The leftmost X-Forwarded-For entry is whatever the client sent, so it can be spoofed.
    Each proxy appends the address it received the request from, so the trustworthy entry
    is the one added by the first proxy we control: counting from the right, skip
    TRUSTED_PROXY_HOPS - 1 entries (default 1 hop: Render's load balancer -> rightmost).
    If the platform sets a header the client cannot forge, name it in TRUSTED_IP_HEADER.
    Verify against the deployment's real headers before relying on per-IP limits; the
    global daily caps are the hard guard either way.
    """
    trusted = os.environ.get("TRUSTED_IP_HEADER", "").strip().lower()
    if trusted and headers.get(trusted):
        return headers.get(trusted).strip()
    fwd = [p.strip() for p in (headers.get("x-forwarded-for") or "").split(",") if p.strip()]
    if fwd:
        hops = max(1, int(os.environ.get("TRUSTED_PROXY_HOPS", "1") or 1))
        return fwd[-hops] if len(fwd) >= hops else fwd[0]
    return peer or "unknown"


def _client_ip(request: Request) -> str:
    return client_ip(request.headers, request.client.host if request.client else None)


def _retry_after(key: str, limit: int, window_s: int, amount: int = 1) -> int:
    """Seconds until `amount` more fits under `limit` in the rolling window (0 = allowed now)."""
    now = time.time()
    q = _rate_events[key]
    while q and q[0][0] <= now - window_s:
        q.popleft()
    used = sum(a for _, a in q)
    if used + amount <= limit:
        return 0
    if amount > limit:
        return window_s
    for ts, a in q:  # oldest first: wait until enough expires
        used -= a
        if used + amount <= limit:
            return max(1, int(ts + window_s - now) + 1)
    return window_s


def _record(key: str, amount: int = 1) -> None:
    _rate_events[key].append((time.time(), amount))


def _wait_text(seconds: int) -> str:
    if seconds >= _HOUR:
        return f"{round(seconds / _HOUR)} h"
    return f"{max(1, round(seconds / 60))} min"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _storage
    _storage = SupabaseAdapter.from_env()
    # Fail loudly (log + Sentry) if a migration in docs/sql/ hasn't been applied.
    app.state.missing_columns = await _storage.missing_columns(REQUIRED_COLUMNS)
    if app.state.missing_columns:
        msg = f"Supabase schema is missing columns {app.state.missing_columns}; apply docs/sql/ migrations"
        print(f"ERROR: {msg}", flush=True)
        sentry_sdk.capture_message(msg, level="error")
    from backend.seed.fsc_incidents import seed_artifacts
    try:
        await seed_artifacts(_storage)
    except Exception as exc:
        print(f"ERROR: knowledge-base seeding failed: {type(exc).__name__}: {exc}", flush=True)
        sentry_sdk.capture_exception(exc)
    try:
        app.state.kb_artifacts = await _storage.count_artifacts()
    except Exception as exc:
        app.state.kb_artifacts = None
        sentry_sdk.capture_exception(exc)
    if not app.state.kb_artifacts:
        print("ERROR: knowledge base is empty; incidents will run without past-incident context", flush=True)
        sentry_sdk.capture_message("knowledge base is empty after startup", level="error")
    yield


app = FastAPI(title="ReconAI", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
        "http://localhost:5199",
        "https://recon-ai-iota.vercel.app",
    ],
    # Starlette does not expand "*" inside allow_origins; preview deploys need a regex.
    allow_origin_regex=r"https://[a-z0-9-]+\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_storage() -> SupabaseAdapter:
    if _storage is None:
        raise HTTPException(status_code=503, detail="Storage not initialized")
    return _storage


StorageDep = Annotated[SupabaseAdapter, Depends(get_storage)]


def _optional(value: str) -> str | None:
    return value.strip() if value and value.strip() else None


def _parse_dt(value: str) -> datetime | None:
    v = (value or "").strip()
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_row(row: dict, run_id: str) -> ReconRow:
    raw_dt = row.get("discrepancy_type", "").strip()
    raw_sev = row.get("severity", "").strip()
    return ReconRow(
        run_id=run_id,
        sf_object=row["sf_object"].strip(),
        sf_field=row["sf_field"].strip(),
        sf_record_id=row["sf_record_id"].strip(),
        sf_value=_optional(row.get("sf_value", "")),
        sf_last_modified=_parse_dt(row.get("sf_last_modified", "")),
        sf_modified_by=_optional(row.get("sf_modified_by", "")),
        db2_table=row["db2_table"].strip(),
        db2_column=row["db2_column"].strip(),
        db2_value=_optional(row.get("db2_value", "")),
        db2_last_updated=_parse_dt(row.get("db2_last_updated", "")),
        last_deployed_at=_parse_dt(row.get("last_deployed_at", "")),
        integration_name=_optional(row.get("integration_name", "")),
        discrepancy_type=DiscrepancyType(raw_dt) if raw_dt else None,
        severity=Severity(raw_sev) if raw_sev else None,
    )


def _severity_sort_key(incident: RCAIncident, row_map: dict[str, ReconRow]) -> int:
    row = row_map.get(str(incident.recon_row_id))
    if not row or not row.severity:
        return 3
    return _SEVERITY_ORDER.get(row.severity, 3)


def _no_confirmed_hypothesis(tested: list[str] | None, ruled_out: list[str] | None) -> bool:
    """True when the graph confirmed nothing: no hypotheses tested, or all of them ruled out."""
    tested = tested or []
    return not tested or set(tested) <= set(ruled_out or [])


def _cached_review_reasons(rca: dict) -> list[str]:
    """Review reasons for a cache entry; derives them for entries written before reasons existed."""
    if "_review_reasons" in rca:
        return list(rca["_review_reasons"])
    reasons = []
    if _no_confirmed_hypothesis(rca.get("_hypotheses_tested"), rca.get("_hypotheses_ruled_out")):
        reasons.append("no_hypothesis_confirmed")
    if float(rca.get("confidence", 0.5)) < 0.75:
        reasons.append("low_confidence")
    if not reasons and rca.get("requires_human_review"):
        reasons.append("legacy_cache_flag")
    return reasons


def _llm_tokens(calls: list[dict]) -> int:
    return sum(c.get("input_tokens", 0) + c.get("output_tokens", 0) for c in calls)


async def _save_incident_and_evidence(storage, incident: RCAIncident, evidence: list[dict]):
    incident_id = await storage.save_rca_incident(incident)
    for ev in evidence:
        try:
            await storage.save_evidence(Evidence(incident_id=incident_id, **ev))
        except Exception:
            pass
    return incident_id


_EVIDENCE_FIELDS = ("source_type", "source_reference", "content", "relevance_explanation",
                   "hypothesis_key", "tool", "tool_args", "outcome", "raw_result")


def _evidence_rows(evidence_collected: list[dict]) -> list[dict]:
    """Every evidence record the graph produced, keyed by its evidence_id (errors and skips included)."""
    return [{"id": ev["evidence_id"], **{k: ev.get(k) for k in _EVIDENCE_FIELDS}}
            for ev in evidence_collected if ev.get("evidence_id")]


def _with_fresh_evidence_ids(evidence: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """Cache replays create a new incident, so its evidence rows need new primary keys.

    Returns the re-keyed rows and the old->new mapping for anything that cites them.
    """
    mapping = {ev["id"]: str(uuid.uuid4()) for ev in evidence if ev.get("id")}
    return [{**ev, "id": mapping.get(ev.get("id"), str(uuid.uuid4()))} for ev in evidence], mapping


def _remap(value, mapping: dict[str, str]):
    """Replace every string that is an old evidence id with its new id, anywhere in a nested value."""
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [_remap(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: _remap(v, mapping) for k, v in value.items()}
    return value


def _similar(candidates: list[dict], limit: int = 5) -> tuple[list[str], list[float]]:
    """The past incidents actually handed to Synthesis (the reranked top `limit`)."""
    top = [c for c in candidates[:limit] if c.get("id")]
    return [str(c["id"]) for c in top], [round(float(c.get("similarity") or 0.0), 4) for c in top]


async def _analyze_row(row: ReconRow, config, graph, storage, bypass_cache: bool = False, session_id: str = "") -> dict:
    """Full analysis pipeline for one row. Returns a result dict; never raises."""
    t0 = time.monotonic()
    cache_key = make_cache_key(row, session_id)
    cached = None if bypass_cache else await check_cache(storage, cache_key)

    if cached:
        rca = cached.get("rca_output") or {}
        confidence = float(rca.get("confidence", 0.5))
        reasons = _cached_review_reasons(rca)
        llm_calls = rca.get("_llm_calls") or []
        cached_evidence, id_map = _with_fresh_evidence_ids(rca.get("_evidence") or [])
        # Cost and trace describe the analysis that produced this result (no new LLM calls are made).
        cost, cost_warnings = incident_cost(llm_calls)
        incident = RCAIncident(
            recon_row_id=row.id,
            similar_incidents=rca.get("_similar_incidents") or [],
            similarity_scores=rca.get("_similarity_scores") or [],
            # Verdicts and claims cite evidence by id; point them at the re-keyed rows.
            **_remap({f: rca[f"_{f}"] for f in _GRAPH_FIELDS if rca.get(f"_{f}") is not None}, id_map),
            **_remap(_explanation_fields(rca), id_map),
            hypotheses_tested=rca.get("_hypotheses_tested") or [],
            hypotheses_ruled_out=rca.get("_hypotheses_ruled_out") or [],
            final_hypothesis=rca.get("_final_hypothesis"),
            total_tool_calls=rca.get("_total_tool_calls") or 0,
            total_tokens_used=rca.get("_total_tokens_used") or _llm_tokens(llm_calls),
            latency_ms=rca.get("_latency_ms") or 0,
            confidence=confidence,
            root_cause_summary=rca.get("root_cause"),
            suggested_fix=rca.get("suggested_fix"),
            postmortem_draft=rca.get("postmortem_draft"),
            jira_summary=rca.get("jira_summary"),
            requires_human_review=bool(reasons),
            review_reasons=reasons,
            llm_calls=llm_calls,
            cost_usd=cost,
            cost_warnings=cost_warnings,
            trace=rca.get("_trace") or [],
            status=IncidentStatus.needs_review if reasons else IncidentStatus.complete,
            llm_model=cached.get("llm_model") or config.synthesis_llm,
        )
        incident.e2e_latency_ms = int((time.monotonic() - t0) * 1000)
        try:
            incident_id = await _save_incident_and_evidence(storage, incident, cached_evidence)
        except Exception as exc:
            return {"incident_id": None, "incident": None, "cached": True, "human_review": bool(reasons), "error": f"save incident: {exc}"}
        return {"incident_id": incident_id, "incident": incident, "cached": True, "human_review": bool(reasons), "error": None}

    try:
        final = await asyncio.to_thread(graph.invoke, initial_state(row.model_dump(mode="json")))
    except Exception as exc:
        return {"incident_id": None, "incident": None, "cached": False, "human_review": False, "error": str(exc)}

    rca = final.get("rca_output") or {}
    reasons = review_reasons(final)
    llm_calls = final.get("llm_calls") or []
    # Synthesis degradation is reported on the incident the way the UI expects it.
    final_hypothesis = "API_UNAVAILABLE" if final.get("synthesis_status") == "api_unavailable" \
        else (final.get("current_hypothesis") or None)
    evidence = _evidence_rows(final.get("evidence_collected") or [])
    similar_ids, similar_scores = _similar(final.get("reranked_candidates") or [])
    cost, cost_warnings = incident_cost(llm_calls)

    incident = RCAIncident(
        recon_row_id=row.id,
        similar_incidents=similar_ids,
        similarity_scores=similar_scores,
        hypothesis_verdicts=final.get("hypothesis_verdicts") or [],
        graph_status=final.get("graph_status"),
        root_cause_category=final.get("root_cause_category"),
        contributing_factors=final.get("contributing_factors") or [],
        graph_version=final.get("graph_version"),
        **_explanation_fields(rca),
        hypotheses_tested=final.get("hypotheses_tested") or [],
        hypotheses_ruled_out=final.get("hypotheses_ruled_out") or [],
        final_hypothesis=final_hypothesis,
        confidence=rca.get("confidence") if rca.get("confidence") is not None else final.get("confidence"),
        root_cause_summary=rca.get("root_cause") or final.get("root_cause"),
        suggested_fix=rca.get("suggested_fix"),
        postmortem_draft=rca.get("postmortem_draft"),
        jira_summary=rca.get("jira_summary"),
        requires_human_review=bool(reasons),
        review_reasons=reasons,
        llm_calls=llm_calls,
        status=IncidentStatus.needs_review if reasons else IncidentStatus.complete,
        llm_model=config.synthesis_llm,
        total_tool_calls=len(final.get("evidence_collected") or []),
        total_tokens_used=_llm_tokens(llm_calls),
        latency_ms=final.get("total_latency_ms") or 0,
        cost_usd=cost,
        cost_warnings=cost_warnings,
        trace=final.get("trace") or [],
        e2e_latency_ms=int((time.monotonic() - t0) * 1000),
        retrieval_error=final.get("retrieval_error"),
    )

    try:
        incident_id = await _save_incident_and_evidence(storage, incident, evidence)
    except Exception as exc:
        return {"incident_id": None, "incident": None, "cached": False, "human_review": bool(reasons), "error": f"save incident: {exc}"}

    degraded = degraded_because(final, reasons)
    if degraded:
        # Don't pin an outage for the cache's lifetime: the next run of this row re-analyzes.
        return {"incident_id": incident_id, "incident": incident, "cached": False, "human_review": bool(reasons),
                "error": None, "degraded": degraded}

    await write_cache(storage, cache_key, {
        **rca,
        "_hypotheses_tested": incident.hypotheses_tested,
        "_hypotheses_ruled_out": incident.hypotheses_ruled_out,
        "_final_hypothesis": incident.final_hypothesis,
        "_review_reasons": reasons,
        "_llm_calls": llm_calls,
        "_trace": incident.trace,
        "_latency_ms": incident.latency_ms,
        "_total_tool_calls": incident.total_tool_calls,
        "_total_tokens_used": incident.total_tokens_used,
        "_evidence": evidence,
        "_similar_incidents": similar_ids,
        "_similarity_scores": similar_scores,
        **{f"_{f}": getattr(incident, f) for f in _GRAPH_FIELDS},
    }, config.synthesis_llm)

    return {"incident_id": incident_id, "incident": incident, "cached": False, "human_review": bool(reasons), "error": None}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/health")
async def health(request: Request):
    """ok | degraded. Degraded = the app answers but the database is unreachable or the
    knowledge base is empty. (A down app doesn't answer at all.)"""
    config = get_config()
    db_ok, kb = True, None
    try:
        kb = await _storage.count_artifacts()
    except Exception:
        db_ok = False
    problems = ([] if db_ok else ["database unreachable"]) + (["knowledge base empty"] if db_ok and not kb else [])
    missing = getattr(request.app.state, "missing_columns", None)
    if missing:
        problems.append("schema migrations missing")
    return {
        "status": "degraded" if problems else "ok",
        "problems": problems,
        "version": "0.1.0",
        "llm_model": config.synthesis_llm,
        "vector_store": "supabase-pgvector",
        "db": "ok" if db_ok else "unreachable",
        "kb_artifacts": kb,
    }


@app.post("/api/v1/recon/runs", status_code=201)
async def create_recon_run(
    request: Request,
    storage: StorageDep,
    file: UploadFile = File(...),
    sf_org_id: str = Form(default="sf-demo-org"),
    db2_environment: str = Form(default="PROD"),
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")
    if db2_environment not in ("PROD", "UAT"):
        raise HTTPException(status_code=400, detail="db2_environment must be PROD or UAT")

    ip = _client_ip(request)
    wait = _retry_after(f"upload:ip:{ip}", UPLOADS_PER_IP_PER_HOUR, _HOUR)
    if wait:
        raise HTTPException(status_code=429, detail=f"Upload limit reached ({UPLOADS_PER_IP_PER_HOUR}/hour). Try again in {_wait_text(wait)}.")
    wait = _retry_after("upload:all", UPLOADS_PER_DAY, _DAY)
    if wait:
        raise HTTPException(status_code=429, detail=f"Daily upload limit reached for the demo. Try again in {_wait_text(wait)}.")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // 1024} KB).")
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
        raw_rows = list(reader)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"CSV parse error: {exc}")

    if not raw_rows:
        raise HTTPException(status_code=422, detail="CSV file is empty")

    if len(raw_rows) > MAX_UPLOAD_ROWS:
        raise HTTPException(status_code=413, detail=f"Too many rows: {len(raw_rows)} (max {MAX_UPLOAD_ROWS} per upload).")

    missing_cols = _REQUIRED_CSV_COLUMNS - set(reader.fieldnames or [])
    if missing_cols:
        raise HTTPException(status_code=422, detail=f"Missing CSV columns: {sorted(missing_cols)}")

    wait = _retry_after("rows:all", ROWS_PER_DAY, _DAY, amount=len(raw_rows))
    if wait:
        raise HTTPException(status_code=429, detail=f"Daily analysis budget for the demo is used up. Try again in {_wait_text(wait)}.")
    _record(f"upload:ip:{ip}")
    _record("upload:all")
    _record("rows:all", len(raw_rows))

    run = ReconRun(
        run_date=date.today(),
        sf_org_id=sf_org_id,
        db2_environment=db2_environment,
        total_rows_checked=len(raw_rows),
        total_discrepancies=len(raw_rows),
        status="pending",
    )

    try:
        run_id = await storage.save_recon_run(run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save run: {exc}")

    try:
        recon_rows = [_parse_row(r, run_id) for r in raw_rows]
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Row validation error: {exc}")

    try:
        row_ids = await storage.save_recon_rows(recon_rows)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save rows: {exc}")

    # Batch embed rows at upload time — failures are non-fatal
    for row, row_id in zip(recon_rows, row_ids):
        text = " ".join(filter(None, [
            row.sf_object,
            row.sf_field,
            row.discrepancy_type.value if row.discrepancy_type else "",
            row.integration_name or "",
        ])).strip()
        if text:
            try:
                embedding = await asyncio.to_thread(embed_text, text)
                await storage.update_recon_row_embedding(row_id, embedding)
            except Exception:
                pass

    return {"run_id": run_id, "rows_accepted": len(row_ids)}


@app.post("/api/v1/recon/runs/{run_id}/analyze", status_code=202)
async def analyze_run(run_id: str, storage: StorageDep):
    rows = await storage.get_recon_rows_for_run(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="No recon rows found for run")

    config = get_config()
    graph = build_graph(config, storage)

    incidents_created = 0
    needs_review_count = 0
    cache_hits = 0
    errors: list[str] = []

    for row in rows:
        result = await _analyze_row(row, config, graph, storage)
        if result["error"]:
            errors.append(f"row {row.id}: {result['error']}")
            continue
        incidents_created += 1
        if result["human_review"]:
            needs_review_count += 1
        if result["cached"]:
            cache_hits += 1

    await storage.update_run_status(
        run_id,
        status="complete",
        completed_at=datetime.now(timezone.utc),
    )

    return {
        "run_id": run_id,
        "rows_processed": len(rows),
        "incidents_created": incidents_created,
        "cache_hits": cache_hits,
        "needs_human_review": needs_review_count,
        "errors": errors,
        "status": "complete",
    }


@app.get("/api/v1/recon/runs/{run_id}/stream")
async def stream_run_analysis(
    run_id: str,
    request: Request,
    storage: StorageDep,
    llm_config: str = Query(default=""),
    session_id: str = Query(default=""),
    bypass_cache: bool = Query(default=False),
    last_event_id: Optional[str] = Header(default=None, alias="last-event-id"),
):
    rows = await storage.get_recon_rows_for_run(run_id)

    if not rows:
        async def _not_found():
            yield f"event: error\ndata: {json.dumps({'detail': 'No recon rows found for run'})}\n\n"
        return StreamingResponse(
            _not_found(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if bypass_cache:
        # Forced re-analysis re-spends LLM calls for every row — rate-limit it.
        ip = _client_ip(request)
        wait = _retry_after(f"bypass:ip:{ip}", BYPASS_CACHE_PER_IP_PER_HOUR, _HOUR) or \
            _retry_after("rows:all", ROWS_PER_DAY, _DAY, amount=len(rows))
        if wait:
            async def _limited():
                msg = f"Re-analysis limit reached. Try again in {_wait_text(wait)}."
                yield f"event: error\ndata: {json.dumps({'detail': msg})}\n\n"
            return StreamingResponse(
                _limited(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        _record(f"bypass:ip:{ip}")
        _record("rows:all", len(rows))

    # Resolve cutoff timestamp from Last-Event-ID so reconnects skip already-sent incidents.
    cutoff_dt = None
    if last_event_id:
        try:
            last_inc = await storage.get_incident_by_id(last_event_id)
            cutoff_dt = last_inc.created_at
        except Exception:
            pass  # unknown id — stream everything

    # If ALL rows already have incidents, stream them without re-analyzing.
    # Partial completion (len < len(rows)) means a prior run was interrupted —
    # fall through to re-analyze so the missing rows get processed.
    existing_incidents = await storage.get_incidents_for_run(run_id)
    if not bypass_cache and existing_incidents and len(existing_incidents) >= len(rows):
        row_map = {str(r.id): r for r in rows}

        async def _stream_existing():
            for i, incident in enumerate(existing_incidents):
                if cutoff_dt and incident.created_at and incident.created_at <= cutoff_dt:
                    continue
                row = row_map.get(str(incident.recon_row_id))
                payload = {
                    "row_index": i,
                    "row_id": str(incident.recon_row_id),
                    "incident_id": str(incident.id),
                    "cached": True,
                    "severity": row.severity.value if row and row.severity else None,
                    "sf_object": row.sf_object if row else None,
                    "sf_field": row.sf_field if row else None,
                    "root_cause_summary": incident.root_cause_summary,
                    "confidence": incident.confidence,
                    "requires_human_review": incident.requires_human_review,
                    "jira_summary": incident.jira_summary,
                    "llm_model": incident.llm_model,
                }
                yield f"id: {incident.id}\n"
                yield f"event: incident\ndata: {json.dumps(payload)}\n\n"
            # Replaying a finished run must not move completed_at (it drives "Duration");
            # only mark runs that finished all rows but were never marked complete.
            try:
                run = await storage.get_recon_run(run_id)
                already_done = run.status == "complete" and run.completed_at is not None
            except Exception:
                already_done = False
            if not already_done:
                await storage.update_run_status(
                    run_id,
                    status="complete",
                    completed_at=datetime.now(timezone.utc),
                )
            yield f"event: done\ndata: {json.dumps({'total_rows': len(existing_incidents)})}\n\n"

        return StreamingResponse(
            _stream_existing(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    config = get_config_by_key(llm_config) if llm_config else get_config()
    graph = build_graph(config, storage)

    async def _generate():
        for i, row in enumerate(rows):
            try:
                result = await _analyze_row(row, config, graph, storage, bypass_cache=bypass_cache, session_id=session_id)
                if result["error"]:
                    payload = {"row_index": i, "row_id": str(row.id), "error": result["error"]}
                    yield f"event: error\ndata: {json.dumps(payload)}\n\n"
                    continue
                incident: RCAIncident = result["incident"]
                if cutoff_dt and incident.created_at and incident.created_at <= cutoff_dt:
                    continue
                payload = {
                    "row_index": i,
                    "row_id": str(row.id),
                    "incident_id": result["incident_id"],
                    "cached": result["cached"],
                    "severity": row.severity.value if row.severity else None,
                    "sf_object": row.sf_object,
                    "sf_field": row.sf_field,
                    "root_cause_summary": incident.root_cause_summary,
                    "confidence": incident.confidence,
                    "requires_human_review": incident.requires_human_review,
                    "jira_summary": incident.jira_summary,
                    "llm_model": incident.llm_model,
                }
                yield f"id: {result['incident_id']}\n"
                yield f"event: incident\ndata: {json.dumps(payload)}\n\n"
            except Exception as exc:
                payload = {"row_index": i, "row_id": str(row.id), "error": str(exc)}
                yield f"event: error\ndata: {json.dumps(payload)}\n\n"
        await storage.update_run_status(
            run_id,
            status="complete",
            completed_at=datetime.now(timezone.utc),
        )
        yield f"event: done\ndata: {json.dumps({'total_rows': len(rows)})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _row_fields(row) -> dict:
    """Fields the run views show for each incident, joined from its recon row."""
    return {
        "severity": row.severity.value if row and row.severity else None,
        "sf_object": row.sf_object if row else None,
        "sf_field": row.sf_field if row else None,
        "discrepancy_type": row.discrepancy_type.value if row and row.discrepancy_type else None,
    }


@app.get("/api/v1/recon/runs/{run_id}")
async def get_run(run_id: str, storage: StorageDep):
    try:
        run = await storage.get_recon_run(run_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Run not found")

    rows = await storage.get_recon_rows_for_run(run_id)
    incidents = await storage.get_incidents_for_run(run_id)
    row_map = {str(r.id): r for r in rows}

    incidents.sort(key=lambda inc: _severity_sort_key(inc, row_map))

    incidents_out = []
    for inc in incidents:
        row = row_map.get(str(inc.recon_row_id))
        d = inc.model_dump(mode="json")
        d.update(_row_fields(row))
        incidents_out.append(d)

    return {
        "run": run.model_dump(mode="json"),
        "incidents": incidents_out,
        "total_incidents": len(incidents),
        "rows_scanned": len(rows),
        "needs_review": sum(1 for i in incidents if i.requires_human_review),
    }


@app.get("/api/v1/recon/runs/{run_id}/incidents")
async def list_run_incidents(run_id: str, storage: StorageDep):
    rows = await storage.get_recon_rows_for_run(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run not found or has no rows")

    incidents = await storage.get_incidents_for_run(run_id)
    row_map = {str(r.id): r for r in rows}

    incidents.sort(key=lambda inc: _severity_sort_key(inc, row_map))

    incidents_out = []
    for inc in incidents:
        row = row_map.get(str(inc.recon_row_id))
        d = inc.model_dump(mode="json")
        d.update(_row_fields(row))
        incidents_out.append(d)

    return {"run_id": run_id, "incidents": incidents_out}


@app.get("/api/v1/incidents/{incident_id}")
async def get_incident(incident_id: str, storage: StorageDep):
    try:
        incident = await storage.get_incident_by_id(incident_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Incident not found")

    evidence = await storage.get_evidence_for_incident(incident_id)
    resolution = await storage.get_resolution_for_incident(incident_id)
    evidence_json = [e.model_dump(mode="json") for e in evidence]

    # Group evidence by hypothesis, in the order the hypotheses were tested.
    order = {h: i for i, h in enumerate(incident.hypotheses_tested)}
    by_hypothesis: dict[str, list[dict]] = {}
    for ev in sorted(evidence_json, key=lambda e: order.get(e.get("hypothesis_key"), len(order))):
        by_hypothesis.setdefault(ev.get("hypothesis_key") or "unlinked", []).append(ev)

    similar = []
    for artifact_id, score in zip(incident.similar_incidents, incident.similarity_scores or []):
        try:
            artifact = await storage.get_artifact(str(artifact_id))
        except Exception:
            continue  # artifact removed since the incident was analyzed
        similar.append({
            "id": str(artifact_id),
            "similarity": score,
            "source": artifact.source,
            "root_cause_category": artifact.root_cause_category,
            "discrepancy_type": artifact.discrepancy_type,
            "summary": artifact.content[:280],
        })

    recon_row = None
    if incident.recon_row_id:
        try:
            recon_row = (await storage.get_recon_row(str(incident.recon_row_id))).model_dump(mode="json")
        except Exception:
            recon_row = None  # row removed; the page shows the incident without it

    return {
        **incident.model_dump(mode="json"),
        "recon_row": recon_row,
        "severity": (recon_row or {}).get("severity"),
        "evidence": evidence_json,
        "evidence_by_hypothesis": by_hypothesis,
        "similar_incidents_detail": similar,
        "resolution": resolution.model_dump(mode="json") if resolution else None,
    }


class ResolveRequest(BaseModel):
    confirmed_root_cause: str
    fix_applied: str = ""
    fix_type: FixType
    fix_verified: bool = False
    resolved_by: str
    correction_notes: Optional[str] = None
    ai_was_correct: Optional[bool] = None


@app.post("/api/v1/incidents/{incident_id}/resolve", status_code=201)
async def resolve_incident(incident_id: str, body: ResolveRequest, storage: StorageDep):
    try:
        await storage.get_incident_by_id(incident_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Incident not found")

    resolution = Resolution(
        incident_id=incident_id,
        confirmed_root_cause=body.confirmed_root_cause,
        fix_applied=body.fix_applied,
        fix_type=body.fix_type,
        fix_verified=body.fix_verified,
        resolved_by=body.resolved_by,
        correction_notes=body.correction_notes,
        ai_was_correct=body.ai_was_correct,
        resolved_at=datetime.now(timezone.utc),
    )

    try:
        resolution_id = await storage.save_resolution(resolution)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save resolution: {exc}")

    return {"resolution_id": resolution_id}


@app.get("/api/v1/recall")
async def get_recall_metrics(storage: StorageDep):
    cached = _recall_cache["data"]
    if cached and (time.time() - _recall_cache["ts"]) < _RECALL_TTL:
        return cached
    try:
        metrics = await asyncio.to_thread(compute_recall_at_k, storage)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Recall computation failed: {exc}")
    _recall_cache["data"] = metrics
    _recall_cache["ts"] = time.time()
    return metrics


# ---------------------------------------------------------------------------
# Analytics endpoints (Slice 8)
# ---------------------------------------------------------------------------

_analytics_cache: dict = {}
_ANALYTICS_TTL = 300  # 5 minutes


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


@app.get("/api/v1/analytics/summary")
async def analytics_summary(storage: StorageDep, days: int = Query(default=30, ge=1)):
    _ck = f"summary:{days}"
    _hit = _analytics_cache.get(_ck)
    if _hit and (time.time() - _hit["ts"]) < _ANALYTICS_TTL:
        return _hit["data"]

    since = _since(days)
    since_prev = _since(days * 2)

    runs_cur = await storage.get_runs_since(since)
    runs_prev_all = await storage.get_runs_since(since_prev)
    runs_prev = [r for r in runs_prev_all if r["created_at"] < since.isoformat()]

    incidents_cur = await storage.get_incidents_since(since)
    incidents_prev_all = await storage.get_incidents_since(since_prev)
    incidents_prev = [i for i in incidents_prev_all if i["created_at"] < since.isoformat()]

    resolutions_cur = await storage.get_resolutions_since(since)

    def _delta_pct(cur: int, prev: int) -> int:
        if prev == 0:
            return 0
        return round((cur - prev) / prev * 100)

    n_runs_cur = len(runs_cur)
    n_runs_prev = len(runs_prev)
    n_inc_cur = len(incidents_cur)
    n_inc_prev = len(incidents_prev)

    res_rate_cur = round(len(resolutions_cur) / n_inc_cur * 100) if n_inc_cur else 0

    res_prev_ids = {i["id"] for i in incidents_prev}
    prev_res = await storage.get_resolutions_since(since_prev)
    prev_res_filtered = [r for r in prev_res if r.get("incident_id") in res_prev_ids]
    res_rate_prev = round(len(prev_res_filtered) / len(incidents_prev) * 100) if incidents_prev else 0

    conf_values = [float(i["confidence"]) for i in incidents_cur if i.get("confidence")]
    avg_conf_cur = round(sum(conf_values) / len(conf_values) * 100) if conf_values else 0
    conf_prev_values = [float(i["confidence"]) for i in incidents_prev if i.get("confidence")]
    avg_conf_prev = round(sum(conf_prev_values) / len(conf_prev_values) * 100) if conf_prev_values else 0

    # top root cause from discrepancy_type of recon_rows
    rows = await storage.get_recon_rows_since(since)
    inc_row_ids = {i["recon_row_id"] for i in incidents_cur if i.get("recon_row_id")}
    disc_counts: dict[str, int] = {}
    for r in rows:
        if r["id"] not in inc_row_ids:
            continue
        dt = r.get("discrepancy_type") or "UNKNOWN"
        disc_counts[dt] = disc_counts.get(dt, 0) + 1
    top_rc_name = max(disc_counts, key=disc_counts.get) if disc_counts else "N/A"
    top_rc_count = disc_counts.get(top_rc_name, 0)
    top_rc_pct = round(top_rc_count / n_inc_cur * 100) if n_inc_cur else 0

    deploys = await storage.get_deployment_events_since(since)
    all_inc_by_date: dict[str, int] = {}
    for inc in incidents_cur:
        dt_str = (inc.get("created_at") or "")[:10]
        all_inc_by_date[dt_str] = all_inc_by_date.get(dt_str, 0) + 1

    baseline_window = 14
    spike_count = 0
    for dep in deploys:
        dep_at_str = dep.get("deployed_at", "")
        try:
            dep_at = datetime.fromisoformat(dep_at_str.replace("Z", "+00:00"))
        except Exception:
            continue
        baseline_dates = [(dep_at - timedelta(days=x)).date().isoformat() for x in range(1, baseline_window + 1)]
        baseline_vals = [all_inc_by_date.get(d, 0) for d in baseline_dates]
        post_date = dep_at.date().isoformat()
        post_count = all_inc_by_date.get(post_date, 0)
        try:
            mean = statistics.mean(baseline_vals)
            std = statistics.stdev(baseline_vals)
            sigma = (post_count - mean) / std if std > 0.01 else 0.0
        except Exception:
            sigma = 0.0
        if sigma >= 3.0:
            spike_count += 1

    _result = {
        "runs": {"count": n_runs_cur, "delta_pct": _delta_pct(n_runs_cur, n_runs_prev)},
        "incidents_triaged": {"count": n_inc_cur, "delta_pct": _delta_pct(n_inc_cur, n_inc_prev)},
        "avg_resolution_rate": {"pct": res_rate_cur, "delta_pt": res_rate_cur - res_rate_prev},
        "avg_confidence": {"pct": avg_conf_cur, "delta_pt": avg_conf_cur - avg_conf_prev},
        "top_root_cause": {"name": top_rc_name, "pct": top_rc_pct, "count": top_rc_count},
        "deploy_correlations": {"count": spike_count, "total_deploys": len(deploys)},
    }
    _analytics_cache[_ck] = {"data": _result, "ts": time.time()}
    return _result


@app.get("/api/v1/analytics/incidents-over-time")
async def analytics_incidents_over_time(storage: StorageDep, days: int = Query(default=30, ge=1)):
    _ck = f"incidents_over_time:{days}"
    _hit = _analytics_cache.get(_ck)
    if _hit and (time.time() - _hit["ts"]) < _ANALYTICS_TTL:
        return _hit["data"]

    since = _since(days)
    incidents = await storage.get_incidents_since(since)
    rows = await storage.get_recon_rows_since(since)
    row_map = {r["id"]: r for r in rows}

    disc_types = ["NULL_DOWNSTREAM", "VALUE_MISMATCH", "STALE_VALUE", "MISSING_RECORD", "DUPLICATE_DOWNSTREAM"]
    dates = [(since + timedelta(days=i)).date().isoformat() for i in range(days)]
    series: dict[str, list[int]] = {dt: [0] * days for dt in disc_types}

    for inc in incidents:
        dt_str = (inc.get("created_at") or "")[:10]
        if dt_str not in dates:
            continue
        idx = dates.index(dt_str)
        row = row_map.get(str(inc.get("recon_row_id", "")))
        disc = row.get("discrepancy_type") if row else None
        if disc and disc in series:
            series[disc][idx] += 1

    deploys = await storage.get_deployment_events_since(since)
    deploy_out = [
        {"date": dep["deployed_at"][:10], "name": dep["deploy_name"]}
        for dep in deploys
    ]

    _result = {"dates": dates, "series": series, "deployments": deploy_out}
    _analytics_cache[_ck] = {"data": _result, "ts": time.time()}
    return _result


@app.get("/api/v1/analytics/by-object")
async def analytics_by_object(storage: StorageDep, days: int = Query(default=30, ge=1)):
    _ck = f"by_object:{days}"
    _hit = _analytics_cache.get(_ck)
    if _hit and (time.time() - _hit["ts"]) < _ANALYTICS_TTL:
        return _hit["data"]

    since = _since(days)
    incidents = await storage.get_incidents_since(since)
    rows = await storage.get_recon_rows_since(since)
    row_map = {r["id"]: r for r in rows}

    obj_counts: dict[str, dict[str, int]] = {}
    for inc in incidents:
        row = row_map.get(str(inc.get("recon_row_id", "")))
        if not row:
            continue
        obj = row.get("sf_object") or "Unknown"
        sev = row.get("severity") or "P3"
        if obj not in obj_counts:
            obj_counts[obj] = {"P1": 0, "P2": 0, "P3": 0}
        if sev in obj_counts[obj]:
            obj_counts[obj][sev] += 1

    _result = [
        {
            "object": obj,
            "p1": counts["P1"],
            "p2": counts["P2"],
            "p3": counts["P3"],
            "total": counts["P1"] + counts["P2"] + counts["P3"],
        }
        for obj, counts in obj_counts.items()
    ]
    _result.sort(key=lambda x: x["total"], reverse=True)
    _analytics_cache[_ck] = {"data": _result, "ts": time.time()}
    return _result


@app.get("/api/v1/analytics/root-cause-distribution")
async def analytics_root_cause_distribution(storage: StorageDep, days: int = Query(default=30, ge=1)):
    _ck = f"root_cause:{days}"
    _hit = _analytics_cache.get(_ck)
    if _hit and (time.time() - _hit["ts"]) < _ANALYTICS_TTL:
        return _hit["data"]

    since = _since(days)
    incidents = await storage.get_incidents_since(since)
    rows = await storage.get_recon_rows_since(since)
    row_map = {r["id"]: r for r in rows}

    counts: dict[str, int] = {}
    total = 0
    for inc in incidents:
        row = row_map.get(str(inc.get("recon_row_id", "")))
        disc = row.get("discrepancy_type") if row else "UNKNOWN"
        key = disc or "UNKNOWN"
        counts[key] = counts.get(key, 0) + 1
        total += 1

    _result = [
        {
            "root_cause": rc,
            "count": cnt,
            "pct": round(cnt / total * 100) if total else 0,
        }
        for rc, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True)
    ]
    _analytics_cache[_ck] = {"data": _result, "ts": time.time()}
    return _result


@app.get("/api/v1/analytics/deployment-correlation")
async def analytics_deployment_correlation(storage: StorageDep, days: int = Query(default=30, ge=1)):
    _ck = f"deploy_corr:{days}"
    _hit = _analytics_cache.get(_ck)
    if _hit and (time.time() - _hit["ts"]) < _ANALYTICS_TTL:
        return _hit["data"]

    since = _since(days)
    # Fetch all incidents for a larger window for baseline calculation
    big_since = _since(days + 14)
    all_incidents = await storage.get_incidents_since(big_since)
    rows = await storage.get_recon_rows_since(big_since)
    row_map = {r["id"]: r for r in rows}

    resolutions = await storage.get_resolutions_since(big_since)
    resolved_incident_ids = {r["incident_id"] for r in resolutions}

    daily_counts: dict[str, int] = {}
    for inc in all_incidents:
        dt_str = (inc.get("created_at") or "")[:10]
        daily_counts[dt_str] = daily_counts.get(dt_str, 0) + 1

    deployments = await storage.get_all_deployment_events()

    result = []
    for dep in deployments:
        dep_at_str = dep.get("deployed_at", "")
        try:
            dep_at = datetime.fromisoformat(dep_at_str.replace("Z", "+00:00"))
        except Exception:
            continue

        if dep_at < since:
            continue

        baseline_dates = [(dep_at - timedelta(days=x)).date().isoformat() for x in range(1, 15)]
        baseline_vals = [daily_counts.get(d, 0) for d in baseline_dates]

        post_start = dep_at
        post_end = dep_at + timedelta(hours=24)
        incidents_24h_list = [
            inc for inc in all_incidents
            if (inc.get("created_at") or "") >= post_start.isoformat()
            and (inc.get("created_at") or "") < post_end.isoformat()
        ]
        incidents_24h = len(incidents_24h_list)

        try:
            mean = statistics.mean(baseline_vals)
            std = statistics.stdev(baseline_vals)
            sigma = round((incidents_24h - mean) / std, 2) if std > 0.01 else 0.0
        except Exception:
            sigma = 0.0

        # Most affected object
        obj_counts: dict[str, int] = {}
        rc_counts: dict[str, int] = {}
        for inc in incidents_24h_list:
            row = row_map.get(str(inc.get("recon_row_id", "")))
            if row:
                obj = row.get("sf_object", "")
                if obj:
                    obj_counts[obj] = obj_counts.get(obj, 0) + 1
                disc = row.get("discrepancy_type", "")
                if disc:
                    rc_counts[disc] = rc_counts.get(disc, 0) + 1

        most_obj = max(obj_counts, key=obj_counts.get) if obj_counts else None
        most_rc = max(rc_counts, key=rc_counts.get) if rc_counts else None

        # Status
        incident_ids_24h = {inc["id"] for inc in incidents_24h_list}
        has_resolution = bool(incident_ids_24h & resolved_incident_ids)
        if sigma >= 3.0 and not has_resolution:
            status = "investigating"
        elif has_resolution:
            status = "resolved"
        else:
            status = "normal"

        result.append({
            "deploy_name": dep["deploy_name"],
            "description": dep.get("description"),
            "deployed_at": dep_at_str,
            "deploy_type": dep.get("deploy_type", ""),
            "incidents_24h": incidents_24h,
            "sigma": sigma,
            "most_affected_object": most_obj,
            "suspected_root_cause": most_rc,
            "status": status,
        })

    result.sort(key=lambda x: abs(x["sigma"]), reverse=True)
    _analytics_cache[_ck] = {"data": result, "ts": time.time()}
    return result


@app.get("/api/v1/analytics/ai-accuracy")
async def analytics_ai_accuracy(storage: StorageDep, weeks: int = Query(default=12, ge=1)):
    _ck = f"ai_accuracy:{weeks}"
    _hit = _analytics_cache.get(_ck)
    if _hit and (time.time() - _hit["ts"]) < _ANALYTICS_TTL:
        return _hit["data"]

    since = _since(weeks * 7)
    resolutions = await storage.get_resolutions_since(since)

    # Recall@k current values (flat line)
    try:
        recall = await asyncio.to_thread(compute_recall_at_k, storage)
        r1_val = round(recall.get("recall@1", 0.0) * 100, 1)
        r3_val = round(recall.get("recall@3", 0.0) * 100, 1)
    except Exception:
        r1_val = 0.0
        r3_val = 0.0

    # Weekly ai_was_correct from resolutions
    weekly_correct: dict[int, list[bool]] = {}
    for res in resolutions:
        if res.get("resolved_at") and res.get("ai_was_correct") is not None:
            try:
                dt = datetime.fromisoformat(res["resolved_at"].replace("Z", "+00:00"))
                delta_days = (datetime.now(timezone.utc) - dt).days
                week_idx = delta_days // 7
                if 0 <= week_idx < weeks:
                    weekly_correct.setdefault(week_idx, []).append(bool(res["ai_was_correct"]))
            except Exception:
                pass

    week_labels = [f"w-{weeks - 1 - i}" for i in range(weeks)]
    recall_at_1 = [r1_val] * weeks
    recall_at_3 = [r3_val] * weeks
    ai_was_correct_series = []
    for i in range(weeks):
        w_idx = weeks - 1 - i
        vals = weekly_correct.get(w_idx, [])
        ai_was_correct_series.append(round(sum(vals) / len(vals) * 100, 1) if vals else 0.0)

    total_res = len(resolutions)
    overrides = sum(1 for r in resolutions if r.get("ai_was_correct") is False)

    _result = {
        "weeks": week_labels,
        "recall_at_1": recall_at_1,
        "recall_at_3": recall_at_3,
        "ai_was_correct": ai_was_correct_series,
        "summary": {
            "recall_at_1": r1_val,
            "recall_at_3": r3_val,
            "resolutions": total_res,
            "overrides": overrides,
        },
    }
    _analytics_cache[_ck] = {"data": _result, "ts": time.time()}
    return _result


@app.post("/api/v1/recon/runs/{run_id}/benchmark")
async def benchmark_run(
    run_id: str,
    request: Request,
    storage: StorageDep,
    n_rows: int = Query(default=2, ge=1, le=3),
):
    rows = await storage.get_recon_rows_for_run(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run not found or has no rows")

    ip = _client_ip(request)
    cost = min(n_rows, len(rows)) * 3  # each sampled row runs under 3 LLM configs
    wait = _retry_after(f"bench:ip:{ip}", BENCHMARKS_PER_IP_PER_HOUR, _HOUR) or \
        _retry_after("rows:all", ROWS_PER_DAY, _DAY, amount=cost)
    if wait:
        raise HTTPException(status_code=429, detail=f"Benchmark limit reached. Try again in {_wait_text(wait)}.")
    _record(f"bench:ip:{ip}")
    _record("rows:all", cost)

    sample = rows[:n_rows]
    results = []

    for config_key in ("claude", "groq", "hybrid"):
        config = get_config_by_key(config_key)
        graph = build_graph(config, storage)
        row_metrics: list[dict] = []

        for row in sample:
            t0 = asyncio.get_event_loop().time()
            result = await _analyze_row(row, config, graph, storage, bypass_cache=True)
            elapsed_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
            if result["error"] or result["incident"] is None:
                continue
            inc: RCAIncident = result["incident"]
            row_metrics.append({
                "latency_ms": elapsed_ms,
                "tokens": inc.total_tokens_used or 0,
                "confidence": float(inc.confidence or 0.0),
            })

        if not row_metrics:
            results.append({
                "config": config_key,
                "model": config.synthesis_llm,
                "avg_latency_ms": 0,
                "avg_tokens": 0,
                "avg_confidence": 0.0,
            })
            continue

        n = len(row_metrics)
        results.append({
            "config": config_key,
            "model": config.synthesis_llm,
            "avg_latency_ms": round(sum(r["latency_ms"] for r in row_metrics) / n),
            "avg_tokens": round(sum(r["tokens"] for r in row_metrics) / n),
            "avg_confidence": round(sum(r["confidence"] for r in row_metrics) / n, 3),
        })

    return {"run_id": run_id, "rows_sampled": len(sample), "results": results}


# ── Tracking endpoints ────────────────────────────────────────────────────────

class PageViewRequest(BaseModel):
    page: str
    session_id: str
    referrer: str = ""
    user_agent: str = ""


class DemoRequestPayload(BaseModel):
    full_name: str
    work_email: str
    company: Optional[str] = None
    session_id: str
    referrer: str = ""


@app.post("/api/v1/track/pageview", status_code=200)
async def track_page_view(body: PageViewRequest, storage: StorageDep):
    try:
        await storage.insert_page_view({
            "page": body.page,
            "session_id": body.session_id,
            "referrer": body.referrer or None,
            "user_agent": body.user_agent or None,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
    return {"ok": True}


@app.post("/api/v1/track/demo-request", status_code=200)
async def track_demo_request(body: DemoRequestPayload, storage: StorageDep):
    name = body.full_name
    email = body.work_email
    company = body.company or None
    now = datetime.now(timezone.utc).isoformat()

    # Supabase insert — columns: id, name, email, company, requested_at, code_sent, notes
    try:
        result = await storage.insert_demo_request({
            "name": name,
            "email": email,
            "company": company,
            "requested_at": now,
        })
        print(f"Demo request insert OK: {result}", flush=True)
    except Exception as exc:
        print(f"Demo request insert FAILED: {exc}", flush=True)
        sentry_sdk.capture_exception(exc)

    # Email notification via Resend
    try:
        import resend as _resend
        _resend.api_key = os.getenv("RESEND_API_KEY", "")
        notify_to = os.getenv("NOTIFY_EMAIL", "")
        if _resend.api_key and notify_to:
            await asyncio.to_thread(
                _resend.Emails.send,
                {
                    "from": "ReconAI <reconai@resend.dev>",
                    "to": [notify_to],
                    "subject": f"ReconAI demo request: {name}",
                    "html": (
                        f"<h2>New demo request</h2>"
                        f"<p><b>Name:</b> {name}</p>"
                        f"<p><b>Email:</b> {email}</p>"
                        f"<p><b>Company:</b> {company or 'Not provided'}</p>"
                        f"<p><b>Time:</b> {now}</p>"
                    ),
                },
            )
            print(f"Resend notification sent to {notify_to}", flush=True)
    except Exception as exc:
        print(f"Resend notification FAILED: {exc}", flush=True)
        sentry_sdk.capture_exception(exc)

    return {"ok": True}
