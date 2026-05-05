"""RAG tools: embedding, artifact retrieval, Haiku-based reranking, and recall@k evaluation.

match_artifacts RPC — run once in Supabase SQL editor before testing:

CREATE OR REPLACE FUNCTION match_artifacts(
  query_embedding vector(1536),
  match_threshold float,
  match_count int
)
RETURNS TABLE (
  id uuid,
  artifact_type text,
  sf_object text,
  sf_field text,
  discrepancy_type text,
  root_cause_category text,
  integration_name text,
  resolution_confirmed boolean,
  confidence_score float,
  content text,
  source text,
  created_at timestamptz,
  resolved_at timestamptz,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    ra.id,
    ra.artifact_type,
    ra.sf_object,
    ra.sf_field,
    ra.discrepancy_type::text,
    ra.root_cause_category,
    ra.integration_name,
    ra.resolution_confirmed,
    ra.confidence_score,
    ra.content,
    ra.source,
    ra.created_at,
    ra.resolved_at,
    1 - (ra.embedding <=> query_embedding) AS similarity
  FROM recon_artifacts ra
  WHERE 1 - (ra.embedding <=> query_embedding) > match_threshold
  ORDER BY ra.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
"""
from __future__ import annotations

import json
import os
import re
import time

import anthropic
import openai

from backend.config import AgentConfig


def embed_text(text: str) -> list[float]:
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
        dimensions=1536,
    )
    return response.data[0].embedding


def retrieve_similar_artifacts(state: dict, storage) -> list[dict]:
    """Embed the current row context and call match_artifacts RPC synchronously."""
    row = state.get("recon_row", {})
    query = " ".join(filter(None, [
        row.get("sf_object"),
        row.get("sf_field"),
        row.get("discrepancy_type"),
        row.get("integration_name"),
        " ".join(state.get("hypotheses_tested") or []),
        " ".join(state.get("hypotheses_ruled_out") or []),
    ])).strip()
    if not query:
        return []
    try:
        embedding = embed_text(query)
        return storage.search_artifacts_sync(embedding, limit=8)
    except Exception:
        return []


def rerank_candidates(
    candidates: list[dict],
    state: dict,
    config: AgentConfig,
) -> list[dict]:
    """Use Haiku to rerank RAG candidates by relevance to the current incident."""
    if not candidates:
        return []

    row = state.get("recon_row", {})
    context = (
        f"Discrepancy: {row.get('discrepancy_type')} on "
        f"{row.get('sf_object')}.{row.get('sf_field')} "
        f"(hypotheses tested: {', '.join(state.get('hypotheses_tested') or [])})"
    )
    candidates_text = "\n".join(
        f"[{i}] {c.get('content', '')[:350]}" for i, c in enumerate(candidates)
    )
    prompt = (
        f"Context: {context}\n\n"
        f"Rank these past incidents by relevance to the context above (most relevant first). "
        f"Return only a JSON array of integer indices, e.g. [2, 0, 4, 1, 3]. "
        f"No explanation.\n\nIncidents:\n{candidates_text}"
    )

    model = config.reranker_llm
    start = time.monotonic()
    raw = ""
    try:
        if model.startswith("claude"):
            client = anthropic.Anthropic()
            msg = client.messages.create(
                model=model,
                max_tokens=64,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = msg.content[0].text.strip()
        else:
            import groq as groq_sdk
            gclient = groq_sdk.Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
            resp = gclient.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=64,
            )
            raw = resp.choices[0].message.content.strip()
    except Exception:
        return candidates[:5]

    try:
        m = re.search(r"\[[\d,\s]+\]", raw)
        indices: list[int] = json.loads(m.group()) if m else list(range(len(candidates)))
    except Exception:
        indices = list(range(len(candidates)))

    reranked: list[dict] = []
    seen: set[int] = set()
    for i in indices:
        if isinstance(i, int) and 0 <= i < len(candidates) and i not in seen:
            reranked.append(candidates[i])
            seen.add(i)
    for i, c in enumerate(candidates):
        if i not in seen:
            reranked.append(c)

    return reranked[:5]


# (query_text, expected_discrepancy_type)
_RECALL_TEST_QUERIES: list[tuple[str, str]] = [
    ("VALUE_MISMATCH Account AnnualRevenue field value mismatch sf db2 discrepancy", "VALUE_MISMATCH"),
    ("VALUE_MISMATCH Opportunity Amount revenue incorrect value integration", "VALUE_MISMATCH"),
    ("NULL_DOWNSTREAM Contact BillingCity null empty downstream field not populated", "NULL_DOWNSTREAM"),
    ("NULL_DOWNSTREAM Account Phone field null value empty downstream", "NULL_DOWNSTREAM"),
    ("STALE_VALUE Account LastModifiedDate stale cache outdated not refreshed lag", "STALE_VALUE"),
    ("STALE_VALUE Contact stale value cache not updated sync delay", "STALE_VALUE"),
    ("MISSING_RECORD Lead record missing downstream not found absent", "MISSING_RECORD"),
    ("MISSING_RECORD Account record not found downstream missing entity", "MISSING_RECORD"),
    ("DUPLICATE_DOWNSTREAM Contact duplicate records downstream multiple rows", "DUPLICATE_DOWNSTREAM"),
    ("DUPLICATE_DOWNSTREAM Account duplicate downstream same key multiple entries", "DUPLICATE_DOWNSTREAM"),
]


def compute_recall_at_k(storage, k_values: list[int] | None = None) -> dict:
    """Compute recall@k against the seeded artifact corpus.

    'Relevant' is defined as: retrieved artifact has the same discrepancy_type
    as the test query. Binary recall — at least one relevant in top-k.
    """
    if k_values is None:
        k_values = [1, 2, 3, 5]
    max_k = max(k_values)
    hits: dict[int, int] = {k: 0 for k in k_values}
    n_queries = 0

    for query_text, expected_type in _RECALL_TEST_QUERIES:
        try:
            embedding = embed_text(query_text)
            results = storage.search_artifacts_sync(embedding, limit=max_k)
        except Exception:
            continue

        n_queries += 1
        retrieved_types = [r.get("discrepancy_type", "") for r in results]

        for k in k_values:
            if expected_type in retrieved_types[:k]:
                hits[k] += 1

    if n_queries == 0:
        return {f"recall@{k}": 0.0 for k in k_values}

    return {f"recall@{k}": round(hits[k] / n_queries, 3) for k in k_values}
