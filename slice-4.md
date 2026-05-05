# Slice 4 — RAG Pipeline + Synthetic Seed Data + Synthesis Agent

## Goal
Build the full RAG pipeline (pgvector), seed 50-100 synthetic FSC incidents, implement LLM-as-reranker, and build the Synthesis Agent with citation enforcement.

## Demo-able When Complete
Full end-to-end RCA: classified row → hypothesis graph → evidence collected → RAG retrieves similar past incidents → reranker scores them → Synthesis Agent produces cited RCAOutput with postmortem draft and Jira summary.

---

## Files to Create/Modify

### `backend/seed/fsc_incidents.py`
Generates 50-100 synthetic resolved FSC incidents for RAG seeding.

Distribution across root causes:
- FLS_STRIPPED: 20 incidents (most common per research)
- DATAWEAVE_TRANSFORM_ERROR: 15 incidents
- CDC_FIELD_EXCLUDED: 12 incidents
- DELIVERY_GAP: 10 incidents
- DAILY_CAP_EXCEEDED: 8 incidents
- CONDITIONAL_PUBLISH_SKIP: 8 incidents
- FIELD_MAPPING_NULL: 7 incidents
- Other/Unknown: 5 incidents (for RAG fallback testing)

Each incident must include:
- realistic sf_object, sf_field, discrepancy_type
- resolution description (what the analyst did)
- fix_type
- confidence_score (0.75-0.99)
- resolution_confirmed: True

Run this script once to populate `recon_artifacts` table.

### `backend/tools/rag_tools.py`
**`search_past_incidents(embedding, pre_filter, top_k=3)`**

Three-stage pipeline:
```python
# Stage 1: Pre-filter (Postgres WHERE)
candidates = supabase.from_("recon_artifacts")
    .select("*")
    .eq("artifact_type", "past_incident")
    .eq("sf_object", pre_filter.sf_object)
    .eq("discrepancy_type", pre_filter.discrepancy_type)
    .eq("resolution_confirmed", True)
    .gte("created_at", ninety_days_ago)
    .execute()

# Fallback widening if < 5 results
if len(candidates) < 5:
    # drop sf_field filter, widen to object level
    # if still < 5, drop discrepancy_type
    
# Stage 2: ANN (cosine similarity via pgvector)
# Stage 3: Post-filter (confidence_score > 0.75, not in ruled_out)
# Return top_k
```

### `backend/agents/synthesis.py`
Synthesis Agent — assembles cited RCA from complete ReconState.

**Citation enforcement:** Before calling LLM, verify that `evidence_collected` is non-empty. For each claim in the output, the LLM is instructed to reference a specific evidence item by index. Pydantic validation checks that `evidence_ids` in RCAOutput are non-empty.

**LLM-as-reranker (runs before synthesis):**
Separate structured call (Haiku) that scores the top-3 RAG candidates for relevance. Output: `RerankedIncidents` with scores and one-line reasoning per candidate. This runs before Synthesis Agent receives context.

**RCAOutput must include:**
- root_cause (from hypothesis graph — not LLM-generated)
- confidence (from hypothesis graph)
- evidence_ids (cited Evidence FKs)
- similar_past_incidents (from RAG, reranked)
- suggested_fix (LLM-generated, grounded in evidence)
- postmortem_draft (LLM-generated, structured: what happened, why, when, fix)
- jira_summary (LLM-generated, 3-sentence max)
- requires_human_review (from state)

---

## Acceptance Criteria
- [ ] 50-100 synthetic incidents seeded in recon_artifacts with embeddings
- [ ] Pre-filter → ANN → post-filter pipeline executes correctly
- [ ] Fallback widening triggers when < 5 pre-filter results
- [ ] LLM-as-reranker returns RerankedIncidents with scores
- [ ] Synthesis Agent produces RCAOutput with non-empty evidence_ids
- [ ] Pydantic validation rejects RCAOutput with empty evidence
- [ ] Postmortem draft and Jira summary generated and stored

## Risk Flag
Embedding 50-100 incidents at seed time costs OpenAI API calls (~$0.001 total — negligible). But if the seed script is run multiple times it will create duplicate artifacts. Add a check: skip seeding if recon_artifacts count > 10.