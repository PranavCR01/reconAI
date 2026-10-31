"""Deterministic stand-in for openai.OpenAI().embeddings.create.

Topic-weighted: shared domain terms (discrepancy types, objects, mechanisms) dominate
the vector, so a short query and a long artifact on the same topic score above the
0.4 match_artifacts threshold, like real embeddings do. Everything else is low-weight
hashed noise so unrelated text stays dissimilar.
"""
from __future__ import annotations

import hashlib
import math
import re
from types import SimpleNamespace as NS

DIMS = 1536
TOPICS = [
    "value_mismatch", "null_downstream", "stale_value", "missing_record", "duplicate_downstream",
    "contact", "account", "financialaccount", "kyc", "address", "lead", "opportunity", "task",
    "cdc", "fls", "dataweave", "apex", "splunk", "cache", "retry", "merge", "picklist", "permission",
]


def embed(text: str) -> list[float]:
    vec = [0.0] * DIMS
    low = text.lower()
    for i, topic in enumerate(TOPICS):
        vec[i] += 3.0 * low.count(topic) ** 0.5
    for token in re.findall(r"[a-z0-9_]+", low):
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        vec[len(TOPICS) + h % (DIMS - len(TOPICS))] += 0.15
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class FakeEmbeddings:
    def __init__(self):
        self.calls: list[str] = []
        self.error: Exception | None = None

    def client(self, *args, **kwargs):
        fake = self

        class _Embeddings:
            def create(self, input, model, **kw):
                texts = input if isinstance(input, list) else [input]
                if fake.error is not None:
                    raise fake.error
                fake.calls.extend(texts)
                return NS(data=[NS(embedding=embed(t)) for t in texts])

        return NS(embeddings=_Embeddings())
