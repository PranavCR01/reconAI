# Slice 7 — Groq Benchmarking + recall@k Display

## Goal
Wire up Groq Llama 3.3 70B as a complete alternative config. Run both configs against the same 50 synthetic FSC discrepancies. Display benchmark results in Run Summary.

## Demo-able When Complete
Side-by-side comparison: "Claude config: 0.89 avg confidence, 4.2s avg latency, $0.003/incident. Groq config: 0.81 avg confidence, 1.8s avg latency, $0.0008/incident."

---

## Tasks

### Wire up Groq config
- `langchain-groq` already in dependencies
- Add Groq LLM instances to `config.py` alongside Claude
- Verify tool use reliability with Llama 3.3 70B — run 10 test incidents, check Pydantic validation error rate
- If Groq drops tool arguments more than 20% of the time, add stricter retry logic (max 3 instead of 2)

### Benchmark runner (`backend/seed/benchmark.py`)
- Takes 50 synthetic incidents with known root causes
- Runs each through Claude config and Groq config
- Records: RCA accuracy (ai_was_correct), latency_ms, total_tokens_used, cost estimate
- Stores results in a `benchmark_runs` table (new table, not in main schema)
- Outputs summary JSON

### recall@k display in RunSummary
```
recall@k = resolved incidents where ai_was_correct = True / total resolved incidents
```
Displayed as a percentage with trend (vs last 7 days of resolutions).

### Cost estimation
```python
def estimate_cost(llm_model: str, tokens: int) -> float:
    rates = {
        "claude-haiku-4-5": 0.00025 / 1000,     # per token approx
        "claude-sonnet-4-6": 0.003 / 1000,
        "llama-3.3-70b-versatile": 0.00059 / 1000,  # Groq pricing
    }
    return tokens * rates.get(llm_model, 0)
```

---

## Acceptance Criteria
- [ ] Groq config runs end-to-end without Pydantic validation errors > 20% of time
- [ ] Benchmark runner produces comparison JSON
- [ ] Run Summary displays recall@k percentage
- [ ] Cost per incident displayed for completed runs
- [ ] LLM config shown in run metadata

## Risk Flag
Groq rate limits on free tier: 6000 tokens/minute for Llama 3.3 70B. Benchmark runner must add delays between incidents or it will hit rate limits mid-run. Add `asyncio.sleep(1)` between Groq-config incidents in benchmark.