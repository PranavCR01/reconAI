from __future__ import annotations

import asyncio
import csv
import io
import json
from contextlib import asynccontextmanager
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.cache.rca_cache import check_cache, make_cache_key, write_cache
from backend.config import get_config, get_config_by_key
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
from backend.storage.supabase_adapter import SupabaseAdapter
from backend.tools.rag_tools import compute_recall_at_k, embed_text

load_dotenv()

_storage: SupabaseAdapter | None = None
_recall_metrics_cache: dict | None = None

_REQUIRED_CSV_COLUMNS = {"sf_object", "sf_field", "sf_record_id", "db2_table", "db2_column"}

_SEVERITY_ORDER = {Severity.P1: 0, Severity.P2: 1, Severity.P3: 2}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _storage
    _storage = SupabaseAdapter.from_env()
    try:
        from backend.seed.fsc_incidents import seed_artifacts
        await seed_artifacts(_storage)
    except Exception:
        pass
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
        "https://*.vercel.app",
    ],
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


async def _analyze_row(row: ReconRow, config, graph, storage, bypass_cache: bool = False) -> dict:
    """Full analysis pipeline for one row. Returns a result dict; never raises."""
    cache_key = make_cache_key(row)
    cached = None if bypass_cache else await check_cache(storage, cache_key)

    if cached:
        rca = cached.get("rca_output") or {}
        confidence = float(rca.get("confidence", 0.5))
        human_review = confidence < 0.75 or bool(rca.get("requires_human_review"))
        status = IncidentStatus.needs_review if human_review else IncidentStatus.complete
        incident = RCAIncident(
            recon_row_id=row.id,
            hypotheses_tested=rca.get("_hypotheses_tested") or [],
            hypotheses_ruled_out=rca.get("_hypotheses_ruled_out") or [],
            total_tool_calls=rca.get("_total_tool_calls") or 0,
            total_tokens_used=rca.get("_total_tokens_used") or 0,
            confidence=confidence,
            root_cause_summary=rca.get("root_cause"),
            suggested_fix=rca.get("suggested_fix"),
            postmortem_draft=rca.get("postmortem_draft"),
            jira_summary=rca.get("jira_summary"),
            requires_human_review=human_review,
            status=status,
            llm_model=cached.get("llm_model") or config.synthesis_llm,
        )
        try:
            incident_id = await storage.save_rca_incident(incident)
        except Exception as exc:
            return {"incident_id": None, "incident": None, "cached": True, "human_review": human_review, "error": f"save incident: {exc}"}
        for ev_data in rca.get("_evidence") or []:
            try:
                await storage.save_evidence(Evidence(
                    incident_id=incident_id,
                    source_type=ev_data["source_type"],
                    source_reference=ev_data["source_reference"],
                    content=ev_data["content"],
                    relevance_explanation=ev_data["relevance_explanation"],
                ))
            except Exception:
                pass
        return {"incident_id": incident_id, "incident": incident, "cached": True, "human_review": human_review, "error": None}

    initial_state = {
        "recon_row": row.model_dump(mode="json"),
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
        "llm_calls": [],
        "tool_calls": [],
        "total_latency_ms": 0,
        "evidence_retry_count": 0,
    }

    try:
        final = await asyncio.to_thread(graph.invoke, initial_state)
    except Exception as exc:
        return {"incident_id": None, "incident": None, "cached": False, "human_review": False, "error": str(exc)}

    rca = final.get("rca_output") or {}
    human_review = bool(final.get("requires_human_review") or rca.get("requires_human_review"))
    status = IncidentStatus.needs_review if human_review else IncidentStatus.complete

    incident = RCAIncident(
        recon_row_id=row.id,
        hypotheses_tested=final.get("hypotheses_tested") or [],
        hypotheses_ruled_out=final.get("hypotheses_ruled_out") or [],
        final_hypothesis=final.get("current_hypothesis") or None,
        confidence=rca.get("confidence") or final.get("confidence"),
        root_cause_summary=rca.get("root_cause") or final.get("root_cause"),
        suggested_fix=rca.get("suggested_fix"),
        postmortem_draft=rca.get("postmortem_draft"),
        jira_summary=rca.get("jira_summary"),
        requires_human_review=human_review,
        status=status,
        llm_model=config.synthesis_llm,
        total_tool_calls=len(final.get("evidence_collected") or []),
        total_tokens_used=sum(
            (c.get("input_tokens", 0) + c.get("output_tokens", 0))
            for c in (final.get("llm_calls") or [])
        ),
        latency_ms=final.get("total_latency_ms") or 0,
    )

    try:
        incident_id = await storage.save_rca_incident(incident)
    except Exception as exc:
        return {"incident_id": None, "incident": None, "cached": False, "human_review": human_review, "error": f"save incident: {exc}"}

    for ev in final.get("evidence_collected") or []:
        er = ev.get("evidence_result")
        if not er:
            continue
        try:
            await storage.save_evidence(Evidence(
                incident_id=incident_id,
                source_type=er["source_type"],
                source_reference=er["source_reference"],
                content=er["content"],
                relevance_explanation=er["relevance_explanation"],
            ))
        except Exception:
            pass

    _evidence_cache = [
        {
            "source_type": ev["evidence_result"]["source_type"],
            "source_reference": ev["evidence_result"]["source_reference"],
            "content": ev["evidence_result"]["content"],
            "relevance_explanation": ev["evidence_result"]["relevance_explanation"],
        }
        for ev in (final.get("evidence_collected") or [])
        if ev.get("evidence_result")
    ]
    await write_cache(storage, cache_key, {
        **rca,
        "_hypotheses_tested": final.get("hypotheses_tested") or [],
        "_hypotheses_ruled_out": final.get("hypotheses_ruled_out") or [],
        "_total_tool_calls": len(final.get("evidence_collected") or []),
        "_total_tokens_used": sum(
            (c.get("input_tokens", 0) + c.get("output_tokens", 0))
            for c in (final.get("llm_calls") or [])
        ),
        "_evidence": _evidence_cache,
    }, config.synthesis_llm)

    return {"incident_id": incident_id, "incident": incident, "cached": False, "human_review": human_review, "error": None}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/health")
async def health():
    config = get_config()
    return {
        "status": "ok",
        "version": "0.1.0",
        "llm_model": config.synthesis_llm,
        "vector_store": "supabase-pgvector",
        "db": "supabase",
    }


@app.post("/api/v1/recon/runs", status_code=201)
async def create_recon_run(
    storage: StorageDep,
    file: UploadFile = File(...),
    sf_org_id: str = Form(default="sf-demo-org"),
    db2_environment: str = Form(default="PROD"),
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")
    if db2_environment not in ("PROD", "UAT"):
        raise HTTPException(status_code=400, detail="db2_environment must be PROD or UAT")

    content = await file.read()
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
        raw_rows = list(reader)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"CSV parse error: {exc}")

    if not raw_rows:
        raise HTTPException(status_code=422, detail="CSV file is empty")

    missing_cols = _REQUIRED_CSV_COLUMNS - set(reader.fieldnames or [])
    if missing_cols:
        raise HTTPException(status_code=422, detail=f"Missing CSV columns: {sorted(missing_cols)}")

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
    storage: StorageDep,
    llm_config: str = Query(default=""),
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

    # If incidents already exist for this run, stream them without re-analyzing.
    # This prevents re-triggering the full analysis pipeline on every SSE reconnect.
    existing_incidents = await storage.get_incidents_for_run(run_id)
    if existing_incidents:
        row_map = {str(r.id): r for r in rows}

        async def _stream_existing():
            for i, incident in enumerate(existing_incidents):
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
                yield f"event: incident\ndata: {json.dumps(payload)}\n\n"
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
                result = await _analyze_row(row, config, graph, storage)
                if result["error"]:
                    payload = {"row_index": i, "row_id": str(row.id), "error": result["error"]}
                    yield f"event: error\ndata: {json.dumps(payload)}\n\n"
                    continue
                incident: RCAIncident = result["incident"]
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
                yield f"event: incident\ndata: {json.dumps(payload)}\n\n"
            except Exception as exc:
                payload = {"row_index": i, "row_id": str(row.id), "error": str(exc)}
                yield f"event: error\ndata: {json.dumps(payload)}\n\n"
        yield f"event: done\ndata: {json.dumps({'total_rows': len(rows)})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
        d["severity"] = row.severity.value if row and row.severity else None
        incidents_out.append(d)

    return {
        "run": run.model_dump(mode="json"),
        "incidents": incidents_out,
        "total_incidents": len(incidents),
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
        d["severity"] = row.severity.value if row and row.severity else None
        incidents_out.append(d)

    return {"run_id": run_id, "incidents": incidents_out}


@app.get("/api/v1/incidents/{incident_id}")
async def get_incident(incident_id: str, storage: StorageDep):
    try:
        incident = await storage.get_incident_by_id(incident_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Incident not found")

    evidence = await storage.get_evidence_for_incident(incident_id)

    return {
        **incident.model_dump(mode="json"),
        "evidence": [e.model_dump(mode="json") for e in evidence],
    }


class ResolveRequest(BaseModel):
    confirmed_root_cause: str
    fix_applied: str
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
    global _recall_metrics_cache
    if _recall_metrics_cache is not None:
        return _recall_metrics_cache
    try:
        metrics = await asyncio.to_thread(compute_recall_at_k, storage)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Recall computation failed: {exc}")
    _recall_metrics_cache = metrics
    return metrics


# ---------------------------------------------------------------------------
# Analytics endpoints (Slice 8)
# ---------------------------------------------------------------------------

def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


@app.get("/api/v1/analytics/summary")
async def analytics_summary(storage: StorageDep, days: int = Query(default=30, ge=1)):
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

    return {
        "runs": {"count": n_runs_cur, "delta_pct": _delta_pct(n_runs_cur, n_runs_prev)},
        "incidents_triaged": {"count": n_inc_cur, "delta_pct": _delta_pct(n_inc_cur, n_inc_prev)},
        "avg_resolution_rate": {"pct": res_rate_cur, "delta_pt": res_rate_cur - res_rate_prev},
        "avg_confidence": {"pct": avg_conf_cur, "delta_pt": avg_conf_cur - avg_conf_prev},
        "top_root_cause": {"name": top_rc_name, "pct": top_rc_pct, "count": top_rc_count},
        "deploy_correlations": {"count": spike_count, "total_deploys": len(deploys)},
    }


@app.get("/api/v1/analytics/incidents-over-time")
async def analytics_incidents_over_time(storage: StorageDep, days: int = Query(default=30, ge=1)):
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

    return {"dates": dates, "series": series, "deployments": deploy_out}


@app.get("/api/v1/analytics/by-object")
async def analytics_by_object(storage: StorageDep, days: int = Query(default=30, ge=1)):
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

    result = [
        {
            "object": obj,
            "p1": counts["P1"],
            "p2": counts["P2"],
            "p3": counts["P3"],
            "total": counts["P1"] + counts["P2"] + counts["P3"],
        }
        for obj, counts in obj_counts.items()
    ]
    result.sort(key=lambda x: x["total"], reverse=True)
    return result


@app.get("/api/v1/analytics/root-cause-distribution")
async def analytics_root_cause_distribution(storage: StorageDep, days: int = Query(default=30, ge=1)):
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

    return [
        {
            "root_cause": rc,
            "count": cnt,
            "pct": round(cnt / total * 100) if total else 0,
        }
        for rc, cnt in sorted(counts.items(), key=lambda x: x[1], reverse=True)
    ]


@app.get("/api/v1/analytics/deployment-correlation")
async def analytics_deployment_correlation(storage: StorageDep, days: int = Query(default=30, ge=1)):
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
    return result


@app.get("/api/v1/analytics/ai-accuracy")
async def analytics_ai_accuracy(storage: StorageDep, weeks: int = Query(default=12, ge=1)):
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

    return {
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


@app.post("/api/v1/recon/runs/{run_id}/benchmark")
async def benchmark_run(
    run_id: str,
    storage: StorageDep,
    n_rows: int = Query(default=2, ge=1, le=3),
):
    rows = await storage.get_recon_rows_for_run(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run not found or has no rows")

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
