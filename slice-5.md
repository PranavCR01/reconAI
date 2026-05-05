# Slice 5 — API Endpoints + SSE Streaming + Cache + Batch Embedding

## Goal
Complete all 8 FastAPI endpoints. Replace synchronous analysis with async job execution + SSE streaming. Add RCA result cache and batch embedding on ingest.

## Demo-able When Complete
Upload CSV via UI (not yet built) or curl → SSE stream shows incidents resolving one by one in real time → all 8 endpoints return correct responses.

---

## Files to Create/Modify

### `backend/main.py` (major update)
All 8 endpoints:

```
POST   /api/v1/recon/runs                           
GET    /api/v1/recon/runs/{run_id}                  
GET    /api/v1/recon/runs/{run_id}/stream           ← SSE
GET    /api/v1/recon/runs/{run_id}/incidents        ← paginated, filterable
GET    /api/v1/recon/incidents/{incident_id}        ← full evidence chain
POST   /api/v1/recon/incidents/{incident_id}/resolve ← stores to RAG
GET    /api/v1/artifacts/stats                      
GET    /api/v1/health                               
```

**POST /recon/runs flow:**
1. Parse CSV → validate each row against ReconRow schema
2. Save ReconRun to Supabase
3. Save all ReconRows to Supabase
4. Kick off background task: batch embed all rows (OpenAI batch API)
5. After embedding complete: kick off LangGraph analysis per row
6. Return run_id immediately

**SSE stream format:**
```python
async def generate_sse(run_id: str):
    async for event in get_run_events(run_id):
        yield f"data: {event.model_dump_json()}\n\n"
```

Events: row_started, hypothesis_tested, tool_called, row_complete, run_complete, error

### `backend/cache/rca_cache.py`
```python
async def get_cached_rca(cache_key: str) -> RCAOutput | None: ...
async def set_cached_rca(cache_key: str, output: RCAOutput, ttl_hours: int = 24): ...

def build_cache_key(row: ClassifiedReconRow) -> str:
    # hash of sf_object + sf_field + discrepancy_type + integration_name
    return hashlib.sha256(f"{row.sf_object}|{row.sf_field}|{row.discrepancy_type}|{row.integration_name}".encode()).hexdigest()
```

Cache stored in `rca_cache` Supabase table. Check cache before graph execution — cache hit returns immediately, SSE emits `row_complete` without running agents.

---

## Acceptance Criteria
- [ ] All 8 endpoints return correct responses
- [ ] CSV upload triggers async analysis (non-blocking)
- [ ] SSE stream emits all event types correctly
- [ ] Cache hit bypasses graph execution
- [ ] Batch embedding runs after upload, before graph
- [ ] Pagination works on incidents endpoint (?page=1&severity=P1)
- [ ] Resolution endpoint stores to recon_artifacts (RAG memory loop)

## Risk Flag
FastAPI SSE + background tasks + LangGraph async execution can produce tricky event loop conflicts. Use `asyncio.Queue` per run_id to buffer SSE events from the background task. Don't try to stream directly from LangGraph callbacks.