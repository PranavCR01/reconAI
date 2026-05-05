from __future__ import annotations

import asyncio
import csv
import io
import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
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
