# ReconAI — CLAUDE.md

## What This Is
AI-powered Salesforce integration reconciliation and RCA tool. Replaces a manual Excel decision tree used by Recon teams to diagnose data discrepancies between Salesforce FSC and downstream systems (DB2, Snowflake).

**Pitch:** "Datadog Bits AI SRE for Salesforce integration pipelines, with the Excel decision tree encoded as a deterministic hypothesis graph."  
**Audience:** Deloitte colleagues + Salesforce engineers. Every architectural choice must be defensible.  
**Full architecture:** see `docs/ADR.md`

---

## Stack
| Layer | Choice |
|---|---|
| Agent orchestration | LangGraph |
| Output validation | Pydantic v2 |
| LLM default | Claude Haiku (classification) + Sonnet (reasoning) |
| LLM comparison | Groq Llama 3.3 70B |
| LLM dev | Ollama (local, never in demo) |
| Embedding | OpenAI text-embedding-3-small (1536 dims) |
| Vector + structured store | Supabase (pgvector + Postgres) |
| Backend | FastAPI on Render |
| Frontend | React + Vite + TypeScript + Tailwind + shadcn/ui (New York) |
| State management | Zustand |
| Charts | Recharts |
| Tables | TanStack Table |
| Streaming | Native SSE (EventSource, no library) |

---

## Repo Structure
```
reconai/
├── backend/
│   ├── agents/          # ingestion.py, hypothesis.py, evidence.py, synthesis.py
│   ├── tools/           # splunk_sim.py, salesforce_sim.py, db2_sim.py, rag_tools.py
│   ├── graph/           # recon_graph.py (LangGraph state machine)
│   ├── models/          # state.py, entities.py, outputs.py
│   ├── storage/         # adapter.py, supabase_adapter.py, sf_adapter.py
│   ├── cache/           # rca_cache.py
│   ├── seed/            # fsc_incidents.py (synthetic FSC data)
│   ├── config.py        # AgentConfig — LLM routing per agent
│   └── main.py          # FastAPI app
├── frontend/
│   └── src/
│       ├── views/       # Upload, LiveAnalysis, IncidentDetail, RunSummary
│       ├── store/       # reconStore.ts (Zustand)
│       └── lib/         # sse.ts
├── data/
│   └── sample_fsc_recon.csv
├── docs/
│   ├── ADR.md
│   └── slices/          # slice-1.md through slice-7.md
└── CLAUDE.md
```

---

## Four Agents — Boundaries Are Hard
- **Ingestion:** classify discrepancy type + severity. Haiku only. No tool calls.
- **Hypothesis:** walk graph, decide next step. Sonnet. Routes to Evidence Agent.
- **Evidence:** execute ALL tool calls. Sonnet. Returns cited EvidenceResult.
- **Synthesis:** assemble RCA from complete state. Sonnet. No tool calls.

Hypothesis decides *what* to check. Evidence *executes* the check. Never merge these.

---

## Non-Negotiables
1. Every `RCAIncident` must have ≥1 `Evidence` row per hypothesis tested. Orchestrator validates before Synthesis runs. No evidence → retry (max 2), not surface.
2. `propose_replay` tool is ALWAYS gated behind human approval. Never auto-execute.
3. Confidence < 0.75 → `requires_human_review = True`. Surfaces separately in UI.
4. Every LLM call logs: model, version, token count, latency.
5. P1 incidents display first in UI regardless of processing order.
6. Pydantic on every agent boundary. Schema violation → retry with error context.
7. Mock tools must vary responses based on input — no hardcoded strings.

---

## Supabase Tables (recon_ prefix)
`recon_runs`, `recon_rows` (includes embedding vector(1536)), `rca_incidents`, `rca_evidence`, `resolutions`, `recon_artifacts` (pgvector + HNSW), `rca_cache`

---

## Workflow Rules
- Read CLAUDE.md at the start of every session
- Read the relevant slice brief before implementing that slice
- `/plan` before any implementation — resolve ambiguities first
- One risk flag after each completed slice
- `/compact` when context gets long
- Never break the non-negotiables above

---

## Slice Plan
| Slice | What | Brief |
|---|---|---|
| 1 | Foundation — schema, models, storage adapter, FastAPI skeleton, sample CSV | `docs/slices/slice-1.md` |
| 2 | Ingestion + Hypothesis Agents, LangGraph state machine, basic tool sims | `docs/slices/slice-2.md` |
| 3 | Evidence Agent, Splunk simulator, parallel fan-out, early termination | `docs/slices/slice-3.md` |
| 4 | RAG pipeline, synthetic FSC seed data, Synthesis Agent, citation enforcement | `docs/slices/slice-4.md` |
| 5 | All 8 API endpoints, SSE streaming, RCA cache, batch embedding | `docs/slices/slice-5.md` |
| 6 | Frontend — all 4 views, SSE client, Zustand, sample data escape hatch | `docs/slices/slice-6.md` |
| 7 | Groq benchmarking, LLM config switcher, recall@k display | `docs/slices/slice-7.md` |

---

## Session Log
| Date | Slice | What shipped | Risk flag |
|---|---|---|---|
| — | — | Architecture + ADR + CLAUDE.md complete | Splunk simulator realism is highest demo risk |
| 2026-05-02 | 1 | Models, storage adapter, FastAPI skeleton, sample CSV — all endpoints verified | supabase-py sync→async upgrade risk on v3 |
| 2026-05-03 | 2 | Slice 2 complete — evidence.py, ingestion.py, hypothesis.py, recon_graph.py, supabase_adapter edit, config fix, /analyze endpoint. All 4 checks pass. | Evidence retry no-ops when tool_calls cleared — re-queue original args in Slice 3 |
| 2026-05-03 | 3 | Slice 3 complete — splunk_sim.py, evidence.py replaced, hypothesis.py H2 evaluation added. Both termination paths verified (H2 early exit + H3 fan-out). | EvidenceResult citations are deterministic strings — not RAG-grounded until Slice 4 |
| 2026-05-03 | 4 | Slice 4 complete — RAG pipeline, 23 seed artifacts embedded, Synthesis Agent producing real LLM output, evidence table populated with cited sources. Full pipeline verified: recon row → hypothesis graph → evidence → RAG → synthesis → postmortem. | RAG similar_incidents returning empty (threshold too high). llm_model not persisted. Fix both in Slice 5. |
| 2026-05-03 | 5 | Slice 5 complete — all 8 endpoints verified, SSE streaming working, resolution endpoint saving to Supabase, evidence populated on hypothesis-graph incidents, cache working (cache_hits: 10 on repeat calls). | llm_model stored inside rca_output JSONB to avoid Supabase schema cache issues with ALTER TABLE columns. |
| 2026-05-04 | 6 | Slice 6 complete — all 4 views built (Upload, LiveAnalysis, IncidentDetail, RunSummary), 42 files, 0 TS errors. SSE streaming, Framer Motion animations, resolution form, all routes navigable. Design matches Claude Design HTML mockups. | Browser testing needed in fresh session — verify SSE connects to real backend, sample data button, resolution form submit |
| 2026-05-04 | 6 (verify) | Browser verification: all 5 checks pass. Fixed CORS bug — added Vite proxy (`/api`→8000) + changed API_URL default to relative `/api/v1`. | Evidence/hypotheses empty (tool_calls=0) in sample runs — non-negotiable #1 gap; hypothesis-graph agents not persisting evidence for this CSV shape. Investigate before demo. |
| 2026-05-04 | 6 (hotfix) | PARTIAL — hypothesis.py expanded with real branches for all 5 discrepancy types, Upload.tsx label fixed, rca_cache cleared. Evidence still empty on test run — hypothesis node may be throwing silent exception on new branches. RESUME: check uvicorn stderr for AttributeError/KeyError in _value_mismatch/_stale_value/_missing_record/_duplicate_downstream methods in hypothesis.py |
| 2026-05-05 | debug | Fixed evidence/hypothesis persistence bug. Root cause: stale uvicorn running pre-hotfix hypothesis.py (no branches for VALUE_MISMATCH/STALE_VALUE/MISSING_RECORD/DUPLICATE_DOWNSTREAM → all fell through to unknown fallback, tool_calls=[], empty evidence). Three additional bugs fixed: (1) hypothesis.py H4 early-termination appended "H4" every loop iteration → deduplicated with `if "H4" not in tested` guard; (2) evidence.py retry path returned `{}` leaving evidence_retry_count=0 forever → now increments counter; (3) main.py cache path created RCAIncident without hypotheses_tested/total_tool_calls → now stored as `_hypotheses_tested/_total_tool_calls` in rca_output blob and read back on cache hit. All 5 discrepancy types verified: VALUE_MISMATCH→[HVM1,HVM2,HVM3]/4 evidence, NULL_DOWNSTREAM→[H1,H2,H3]/5 evidence, STALE_VALUE→[HSV1,HSV2]/2 evidence, DUPLICATE_DOWNSTREAM→[HDD1,HDD2]/2 evidence. | Slice 7 (Groq benchmarking) is the only remaining slice — ready to implement. |
| 2026-05-05 | hotfix | All 5 discrepancy types now produce non-empty hypotheses_tested. Root cause was two uvicorn processes on port 8000 — old pre-fix process still handling requests. Code was already correct. Fixed by killing orphan processes, clearing cache, fresh restart. | Always verify only one Python process on port 8000 before debugging — run `netstat -ano \| findstr :8000` |
| 2026-05-05 | 6+hotfix | Full end-to-end verified in browser. Upload, LiveAnalysis, IncidentDetail, RunSummary all working. One remaining gap: Evidence section shows 0 sources on IncidentDetail even though rca_evidence rows exist in Supabase. Frontend is not fetching/displaying evidence correctly. Fix this before demo. | — |
| 2026-05-05 | hotfix | Evidence display fixed — cache hit path now re-saves evidence to rca_evidence for new incident UUID. Full end-to-end verified: Upload → LiveAnalysis → IncidentDetail with evidence cards → RunSummary all working in browser. Core build complete. Ready for Slice 7 (Groq benchmarking). | — |
