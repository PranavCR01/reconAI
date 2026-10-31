"""Metric functions for the eval suite. Pure Python, no dependencies, unit-tested."""
from __future__ import annotations

import math
from collections import Counter
from typing import Iterable, Sequence

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """95% Wilson score interval for k successes out of n (None when n == 0)."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def rate(k: int, n: int) -> dict:
    """A proportion with its count, denominator and 95% Wilson interval."""
    return {"k": k, "n": n, "rate": round(k / n, 4) if n else None, "ci95": wilson(k, n)}


def proportion(flags: Iterable[bool]) -> dict:
    flags = list(flags)
    return rate(sum(1 for f in flags if f), len(flags))


def confusion(pairs: Iterable[tuple[str, str | None]]) -> dict[str, dict[str, int]]:
    """{label: {predicted: count}}, with None predictions shown as 'NONE'. Keys sorted for stable output."""
    table: dict[str, Counter] = {}
    for label, predicted in pairs:
        table.setdefault(label, Counter())[predicted or "NONE"] += 1
    return {label: dict(sorted(counts.items())) for label, counts in sorted(table.items())}


def precision_recall(predicted: Sequence[bool], actual: Sequence[bool]) -> dict:
    """Precision/recall of a binary decision; None where the denominator is empty."""
    tp = sum(1 for p, a in zip(predicted, actual) if p and a)
    fp = sum(1 for p, a in zip(predicted, actual) if p and not a)
    fn = sum(1 for p, a in zip(predicted, actual) if not p and a)
    tn = sum(1 for p, a in zip(predicted, actual) if not p and not a)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": rate(tp, tp + fp), "recall": rate(tp, tp + fn)}


# Buckets from data/benchmark_ground_truth.json evaluation_guide, plus one below 0.5.
ECE_EDGES = (0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


def ece(confidences: Sequence[float | None], correct: Sequence[bool], edges: Sequence[float] = ECE_EDGES) -> dict:
    """Expected calibration error: sum over buckets of |mean confidence - accuracy| * share.

    Items with no confidence are excluded (and counted). A bucket is [lo, hi), the last is [lo, hi].
    """
    items = [(c, ok) for c, ok in zip(confidences, correct) if c is not None]
    buckets = []
    total = len(items)
    error = 0.0
    for i, (lo, hi) in enumerate(zip(edges, edges[1:])):
        last = i == len(edges) - 2
        inside = [(c, ok) for c, ok in items if lo <= c < hi or (last and c == hi)]
        if not inside:
            continue
        mean_conf = sum(c for c, _ in inside) / len(inside)
        acc = sum(1 for _, ok in inside if ok) / len(inside)
        error += abs(mean_conf - acc) * len(inside) / total
        buckets.append({"range": [lo, hi], "n": len(inside), "mean_confidence": round(mean_conf, 4),
                        "accuracy": round(acc, 4)})
    return {"ece": round(error, 4) if total else None, "n": total,
            "excluded_no_confidence": len(confidences) - total, "buckets": buckets}


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float | None:
    """Share of the relevant items found in the top k (None when nothing is relevant)."""
    if not relevant:
        return None
    return len(set(ranked[:k]) & relevant) / len(relevant)


def hit_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> bool | None:
    if not relevant:
        return None
    return bool(set(ranked[:k]) & relevant)


def reciprocal_rank(ranked: Sequence[str], relevant: set[str]) -> float | None:
    if not relevant:
        return None
    for i, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / i
    return 0.0


def mean(values: Iterable[float | None]) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 4) if values else None


def percentile(values: Iterable[float | None], q: float) -> float | None:
    """Nearest-rank percentile (q in [0, 100]); None for no values."""
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    rank = max(1, math.ceil(q / 100 * len(values)))
    return values[rank - 1]


def agreement(runs: Sequence[Sequence]) -> dict:
    """runs[i] = the values one incident got across repeated runs. Agreement = all runs identical."""
    return proportion(len(set(map(_hashable, values))) == 1 for values in runs)


def _hashable(value):
    if isinstance(value, list):
        return tuple(_hashable(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _hashable(v)) for k, v in value.items()))
    return value
