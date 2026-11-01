# Slice 3 — Evidence Agent + Splunk Simulator + Full Hypothesis Graph

## Goal
Build the Evidence Agent, realistic Splunk log simulator, and complete the hypothesis graph for all 5 discrepancy types. Replace H2 stub with real Splunk triage logic.

## Demo-able When Complete
Full hypothesis graph runs end-to-end for all 5 discrepancy types. Evidence collected and cited at each step. Root cause returned with structured EvidenceResult. No RAG yet, no synthesis yet.

---

## Files to Create/Modify

### `backend/tools/splunk_sim.py`
The highest-risk simulator — must feel real. Key behaviors:

**`query_splunk_event_journey(record_id, sf_object, time_window)`**
Returns a structured result covering all three signals in one call:
- `publish_log`: did SF fire the platform event? (include realistic replayId, EventUuid, timestamp)
- `middleware_log`: did MuleSoft/Boomi receive it? (correlationId, flow name, status)
- `target_write_log`: did DB2 get the write? (table, column, value written)

Scenario distribution (varies by sf_object + sf_field):
- 30%: all three present, field still null → Result D (transform error path)
- 25%: publish present, no middleware → Result B (delivery gap)
- 20%: middleware present with ERROR → Result C (DataWeave error)
- 15%: no publish log → Result A (publish failure / cap hit)
- 10%: no logs at all → Result E (Splunk inconclusive)

Log format must look like real Splunk output:
```
2024-01-15 09:24:11.432 INFO  EventBus.Publish [replayId=84721] 
  eventType=ContactChangeEvent recordId=003xx... correlationId=mule-abc123
```

**`get_platform_event_usage(date, sf_org_id)`**
Returns daily delivery usage. 10% chance of cap breach scenario (returns usage > 50000 for Performance org).

**`query_splunk_field_transform(record_id, flow_name, sf_field)`**
Returns field-level transform log. Used in H4 (transform deep dive).
- 60% chance of null coercion bug (DataWeave treating empty string as null)
- 40% chance of picklist mismatch (SF value not in DB2 enum)

### `backend/agents/evidence.py`
Evidence Agent — all tool calls happen here.

Takes `HypothesisDecision` specifying which tools to call. Executes them. Returns `EvidenceResult` with mandatory citation.

**Validation:** Every `EvidenceResult` must have non-empty `source_reference` and `content`. If a tool returns empty/error, Evidence Agent retries once with broader parameters, then returns `EvidenceResult` with `confirms=None` and `rules_out=[]` — never surfaces empty evidence as a claim.

### `backend/graph/recon_graph.py` (update)
Complete all 5 hypothesis graphs:
- NULL_DOWNSTREAM: H1 → H2(Splunk) → H3(parallel) → H4 → H5(RAG stub)
- MISSING_RECORD: replay window check → daily cap → trigger conditions → sharing rules
- VALUE_MISMATCH: field history (which system wrote last) → competing update check → DataWeave mapping
- DUPLICATE_DOWNSTREAM: replay-ID checkpoint → multiple subscribers → idempotency key
- STALE_VALUE: consumer lag → Snowpipe boundary → retry loop state

---

## Acceptance Criteria
- [ ] Splunk simulator returns all 5 result types, distributed realistically
- [ ] Evidence Agent never surfaces a claim without source_reference
- [ ] All 5 hypothesis graphs execute end-to-end without error
- [ ] Retry logic fires when tool returns empty result
- [ ] EvidenceResult Pydantic validation catches missing citations

## Risk Flag
The Splunk simulator's log format needs to be consistent enough that the Synthesis Agent (Slice 4) can parse citations from it reliably. Establish a fixed log line format in Slice 3 — don't change it in Slice 4.