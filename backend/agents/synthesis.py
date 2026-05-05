"""Synthesis Agent — single Sonnet call producing root_cause, suggested_fix,
postmortem_draft, and jira_summary in one JSON response.

evidence_ids is emitted as [] here; main.py fills it post-graph after saving
Evidence rows to Supabase and collecting their IDs.
"""
from __future__ import annotations

import json
import re
import time

from pydantic import ValidationError

from backend.config import AgentConfig
from backend.models.outputs import RCAOutput
from backend.models.state import ReconState

_MAX_RETRIES = 2


def _build_prompt(state: ReconState, error_context: str = "") -> str:
    row = state["recon_row"]
    evidence = state.get("evidence_collected") or []
    candidates = state.get("reranked_candidates") or state.get("rag_candidates") or []
    hypotheses_tested = state.get("hypotheses_tested") or []
    hypotheses_ruled_out = state.get("hypotheses_ruled_out") or []
    hypothesis_root_cause = state.get("root_cause")

    ev_lines = []
    for e in evidence:
        er = e.get("evidence_result") or {}
        content = er.get("content") or str(e.get("result", ""))[:300]
        source = er.get("source_reference", "unknown")
        h_key = e.get("hypothesis_key", "?")
        confirms = er.get("confirms") or ""
        ev_lines.append(f"  [{h_key}] {source}: {content}" + (f" → {confirms}" if confirms else ""))
    evidence_block = "\n".join(ev_lines) if ev_lines else "  No evidence collected."

    rag_lines = []
    for c in candidates[:5]:
        content = c.get("content", "")[:400]
        src = c.get("source", "")
        rag_lines.append(f"  - ({src}) {content}")
    rag_block = "\n".join(rag_lines) if rag_lines else "  No similar past incidents found."

    hypothesis_hint = (
        f"\nHypothesis agent identified root cause: {hypothesis_root_cause}"
        if hypothesis_root_cause
        else "\nHypotheses H1–H3 were inconclusive. Derive root cause from evidence and past incidents."
    )

    error_note = f"\n\nPrevious attempt failed validation: {error_context}\nCorrect those issues." if error_context else ""

    return f"""You are a Salesforce FSC integration RCA analyst. Produce a concise, technically precise root cause analysis.

Record: {row.get('sf_object')}.{row.get('sf_field')} (ID: {row.get('sf_record_id')})
Discrepancy type: {row.get('discrepancy_type')} | Severity: {row.get('severity')}
Integration: {row.get('integration_name') or 'unknown'}
{hypothesis_hint}

Hypotheses tested: {', '.join(hypotheses_tested) or 'none'}
Hypotheses ruled out: {', '.join(hypotheses_ruled_out) or 'none'}

Evidence collected:
{evidence_block}

Similar past incidents (RAG — use for context, not verbatim):
{rag_block}

Respond with a JSON object containing exactly these fields:
{{
  "root_cause": "Concise technical root cause in 1-2 sentences.",
  "suggested_fix": "Actionable remediation steps in 2-4 sentences.",
  "postmortem_draft": "Postmortem narrative suitable for a Confluence page in 3-5 sentences.",
  "jira_summary": "One-line Jira ticket title (under 100 characters).",
  "confidence": <float between 0.0 and 1.0>
}}

Return only the JSON object. No markdown fences. No extra text.{error_note}"""


def _call_llm(prompt: str, model: str) -> tuple[str, int, int, int]:
    """Returns (raw_text, input_tokens, output_tokens, latency_ms)."""
    start = time.monotonic()
    if model.startswith("claude"):
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        input_tokens = msg.usage.input_tokens
        output_tokens = msg.usage.output_tokens
    else:
        import os
        import groq as groq_sdk
        gclient = groq_sdk.Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
        resp = gclient.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        raw = resp.choices[0].message.content.strip()
        usage = resp.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

    latency_ms = int((time.monotonic() - start) * 1000)
    return raw, input_tokens, output_tokens, latency_ms


def _parse_and_validate(raw: str) -> tuple[dict, str]:
    """Returns (parsed_data, error_message). error_message is empty on success."""
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return {}, "No JSON object found in response"
        data = json.loads(m.group())
    except json.JSONDecodeError as exc:
        return {}, f"JSON parse error: {exc}"

    try:
        RCAOutput(
            root_cause=data.get("root_cause", ""),
            confidence=float(data.get("confidence", 0)),
            evidence_ids=[],
            similar_past_incidents=[],
            suggested_fix=data.get("suggested_fix", ""),
            postmortem_draft=data.get("postmortem_draft", ""),
            jira_summary=data.get("jira_summary", ""),
            requires_human_review=float(data.get("confidence", 0)) < 0.75,
        )
    except (ValidationError, ValueError, TypeError) as exc:
        return {}, f"Pydantic validation failed: {exc}"

    if not data.get("root_cause"):
        return {}, "root_cause field is empty"
    if not data.get("suggested_fix"):
        return {}, "suggested_fix field is empty"

    return data, ""


def run_synthesis(state: ReconState, config: AgentConfig) -> dict:
    model = config.synthesis_llm

    total_input_tokens = 0
    total_output_tokens = 0
    total_latency_ms = 0
    data: dict = {}
    error_context = ""

    for attempt in range(_MAX_RETRIES):
        prompt = _build_prompt(state, error_context)
        try:
            raw, in_tok, out_tok, lat_ms = _call_llm(prompt, model)
        except Exception as exc:
            error_context = str(exc)
            total_latency_ms += 0
            continue

        total_input_tokens += in_tok
        total_output_tokens += out_tok
        total_latency_ms += lat_ms

        parsed, error_context = _parse_and_validate(raw)
        if not error_context:
            data = parsed
            break

    root_cause = data.get("root_cause") or state.get("root_cause") or "Root cause undetermined — requires human review."
    confidence = float(data.get("confidence", 0.5))
    suggested_fix = data.get("suggested_fix") or "Manual investigation required by on-call engineer."
    postmortem_draft = data.get("postmortem_draft") or ""
    jira_summary = data.get("jira_summary") or f"RCA: {root_cause[:80]}"
    requires_human_review = confidence < 0.75

    rca_output = RCAOutput(
        root_cause=root_cause,
        confidence=confidence,
        evidence_ids=[],
        similar_past_incidents=[],
        suggested_fix=suggested_fix,
        postmortem_draft=postmortem_draft,
        jira_summary=jira_summary,
        requires_human_review=requires_human_review,
    )

    llm_call_entry = {
        "agent": "synthesis",
        "model": model,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "latency_ms": total_latency_ms,
    }

    return {
        "rca_output": rca_output.model_dump(mode="json"),
        "root_cause": root_cause,
        "confidence": confidence,
        "requires_human_review": requires_human_review,
        "llm_calls": (state.get("llm_calls") or []) + [llm_call_entry],
        "total_latency_ms": (state.get("total_latency_ms") or 0) + total_latency_ms,
    }
