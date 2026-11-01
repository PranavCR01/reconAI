# Slice 2 — Ingestion + Hypothesis Agents + LangGraph State Machine

## Goal
Build the first two agents and wire them into a LangGraph graph. Implement basic tool simulators for DB2 and Salesforce metadata. The graph should run a NULL_DOWNSTREAM discrepancy through H1 → H3 and return a hypothesis decision.

## Demo-able When Complete
Submit a classified ReconRow → LangGraph graph executes → Ingestion Agent classifies → Hypothesis Agent walks H1 → H2 → H3 → returns structured HypothesisDecision with reasoning. No Splunk yet, no synthesis yet.

---

## Prerequisites
Slice 1 complete. All Pydantic models available. Supabase schema live.

---

## Files to Create/Modify

### `backend/agents/ingestion.py`
Ingestion Agent — deterministic classification, no LLM needed for most cases.

**Severity derivation (deterministic, no LLM):**
```
P1: db2_environment == PROD AND sf_object in CORE_FSC_OBJECTS AND discrepancy_type == NULL_DOWNSTREAM
P2: db2_environment == PROD AND sf_object NOT in CORE_FSC_OBJECTS
    OR db2_environment == UAT AND sf_object in CORE_FSC_OBJECTS
P3: everything else
```

CORE_FSC_OBJECTS = ['Contact', 'Account', 'FinancialAccount__c', 'FinancialHolding__c', 'Lead', 'Opportunity']

**Discrepancy classification (deterministic from values):**
- sf_value is not None AND db2_value is None → NULL_DOWNSTREAM
- sf_value is None AND db2_value is None AND record exists in SF but not DB2 → MISSING_RECORD
- Both have values AND they differ → VALUE_MISMATCH
- Multiple DB2 rows for one sf_record_id → DUPLICATE_DOWNSTREAM
- Values match AND db2_last_updated is >threshold behind sf_last_modified → STALE_VALUE

Only use LLM (Haiku) if classification is ambiguous — e.g. both values are null but context suggests different root causes.

Output: `ClassifiedReconRow` (Pydantic)

**Deployment correlation flag:** if `last_deployed_at` is within 24h before `sf_last_modified`, add `deployment_correlated: True` to the classified row. This is a strong signal passed to Hypothesis Agent.

### `backend/agents/hypothesis.py`
Hypothesis Agent — walks the graph, routes conditionally.

Implement NULL_DOWNSTREAM graph only in this slice:
```
H1: check field history in DB2
    → tool: query_db2_field_history
    YES (was populated) → route to H4 (overwrite — stub for now)
    NO → continue to H2

H2: Splunk triage (STUB in this slice — always return "inconclusive")
    → continue to H3

H3: parallel fan-out — FLS + CDC + Apex (all three)
    → tools: get_field_permissions, get_cdc_field_config, get_apex_trigger_config
    → first confirmed → terminate with root cause
    → all pass → route to H5 (RAG — stub for now)
```

Output: `HypothesisDecision` (Pydantic)

**Deployment correlation shortcut:** if `deployment_correlated == True` on the recon row, add a note in reasoning but do NOT skip the graph — deployment correlation is a signal, not a root cause.

### `backend/tools/db2_sim.py`
Realistic DB2 simulator. Must vary responses based on input.

```python
def query_db2_field_history(
    sf_object: str,
    sf_field: str,
    sf_record_id: str,
    time_window_days: int = 30
) -> FieldHistoryResult:
```

Logic:
- If sf_field contains "Status" or "Verification" → 60% chance field was previously populated (simulates status transition scenarios)
- If sf_object == "KYC_Record__c" → 40% chance field was previously populated
- Otherwise → 20% chance
- Always return realistic DB2 column names (snake_case, uppercase: CITY_NM, STATE_CD, ANNINC, etc.)
- Include a `last_value` and `last_updated_at` when was_populated = True

### `backend/tools/salesforce_sim.py`
Realistic Salesforce metadata simulator. Must vary based on input.

**`get_field_permissions(integration_user, sf_object, sf_field)`**
- Fields ending in `__c` (custom) → 35% chance integration user lacks read access
- Standard fields on Contact (Phone, Email, MailingCity) → 15% chance
- FinancialAccount__c fields → 45% chance (FSC-specific, complex permission sets)
- Always return realistic SF API names and permission set names

**`get_cdc_field_config(sf_object, sf_field)`**
- Long text fields, encrypted fields → always excluded from CDC
- Rich text, formula fields → always excluded
- Standard fields → 90% included
- Custom fields → 75% included

**`get_apex_trigger_config(sf_object)`**
- Return simulated trigger metadata: trigger name, events (before insert, after update, etc.), has conditional publish logic (bool)
- KYC_Record__c and Address__c → higher chance of conditional publish logic

### `backend/graph/recon_graph.py`
LangGraph state machine.

```python
from langgraph.graph import StateGraph, END
from backend.models.state import ReconState

def build_graph(config: AgentConfig) -> StateGraph:
    graph = StateGraph(ReconState)
    
    graph.add_node("ingestion", ingestion_node)
    graph.add_node("hypothesis", hypothesis_node)
    graph.add_node("evidence", evidence_node)      # stub for now
    graph.add_node("synthesis", synthesis_node)    # stub for now
    
    graph.set_entry_point("ingestion")
    graph.add_edge("ingestion", "hypothesis")
    graph.add_conditional_edges(
        "hypothesis",
        route_hypothesis,           # returns next node name
        {
            "evidence": "evidence",
            "synthesis": "synthesis",
            END: END
        }
    )
    
    return graph.compile()
```

**Safety:** `iterations` field in ReconState increments on every hypothesis node execution. If `iterations > 15`, force route to synthesis with `requires_human_review = True`. Prevents infinite loops.

### `backend/main.py` (update)
Add endpoint:
```
POST /api/v1/recon/runs/{run_id}/analyze
```
Triggers graph execution for all rows in a run. For this slice — synchronous (we add async + SSE in Slice 5). Returns first completed incident as proof of concept.

---

## Acceptance Criteria
- [ ] Ingestion Agent correctly classifies all 5 discrepancy types from sample CSV
- [ ] Severity derived deterministically without LLM for unambiguous cases
- [ ] Deployment correlation flag set correctly on sample rows
- [ ] Hypothesis Agent walks H1→H2(stub)→H3 for NULL_DOWNSTREAM
- [ ] H3 runs FLS, CDC, and Apex checks (parallel fan-out via LangGraph)
- [ ] Early termination fires when FLS or CDC check confirms root cause
- [ ] Tool simulators return varied responses based on input (verify with 5+ different inputs)
- [ ] LangGraph graph compiles and executes without error
- [ ] Iterations safety counter works — manually test by forcing >15 iterations
- [ ] `HypothesisDecision` Pydantic model validated on every output

## Risk Flag
LangGraph's parallel fan-out syntax (Send API) changed between versions — pin `langgraph>=0.2.0` and verify the parallel node execution pattern works before building H3 logic on top of it.
