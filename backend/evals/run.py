"""Eval runner.

    python -m backend.evals.run --mode offline --config claude
    python -m backend.evals.run --mode live --config claude --runs 3 --yes

Writes evals/results/<mode>_<config>.json (schema: backend/evals/schema.py) and a
matching .md report. Every incident goes through the production analysis path
(`_analyze_row`), against the in-memory fake database.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.evals import metrics as M
from backend.evals.harness import LiveRunRefused, environment
from backend.evals.labels import GROUND_TRUTH, ROOT, SCENARIOS, load_incidents, relevant_sources, sha256_file

RESULTS_DIR = ROOT / "evals" / "results"
SCHEMA_VERSION = 1

CAVEATS = [
    "Dataset: 50 synthetic incidents written and labeled by the project author; not production data.",
    "Tool results come from simulators driven by a declared fault per record (data/scenarios.json), with "
    "seeded confounders. Graph accuracy therefore measures whether the diagnosis logic finds the declared "
    "fault through noise; it is not an estimate of real-world accuracy.",
    "All rates carry 95% Wilson intervals; with n=50 an interval is roughly +/-10 points or wider.",
]
OFFLINE_CAVEAT = ("Offline mode uses a scripted LLM: explanation, critic-LLM, consistency, final-confidence, token "
                  "and cost numbers describe that script, not a model. Only graph metrics, the deterministic critic "
                  "stage and the ablations are meaningful offline.")


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------
class _CapturingGraph:
    """Passes through to the real graph and keeps the last final state for scoring."""

    def __init__(self, graph):
        self._graph = graph
        self.last: dict | None = None

    def invoke(self, state, *args, **kwargs):
        self.last = None
        self.last = self._graph.invoke(state, *args, **kwargs)
        return self.last


def benchmark_row(incident: dict):
    from backend.tests.helpers import ground_truth_row

    return ground_truth_row(incident)


def _deciding_kind(tested: list[str]) -> str | None:
    from backend.graph.hypotheses import BY_ID

    return BY_ID[tested[-1]].kind if tested else None


def _grounded(final: dict) -> bool | None:
    """For an accepted explanation: every claim passes the deterministic checks, nothing cites an
    unknown id, and the root cause names the confirmed category and cites supporting evidence from the
    confirmed hypothesis's own check. None when the explanation wasn't accepted."""
    from backend.agents.explanation import deterministic_checks

    if final.get("judge_decision") != "accept":
        return None
    claims = (final.get("proposal") or {}).get("claims") or []
    if any(deterministic_checks(c, final) for c in claims):
        return False
    if any(str(x).startswith("UNKNOWN:") for c in claims for x in c["evidence_ids"] + c["similar_incident_ids"]):
        return False
    root = next((c for c in claims if c["kind"] == "root_cause"), None)
    confirmed = next((v["hypothesis_id"] for v in final.get("hypothesis_verdicts") or [] if v["verdict"] == "confirmed"), None)
    if root is None or root.get("category") != final.get("root_cause_category"):
        return False
    by_id = {e["evidence_id"]: e for e in final.get("evidence_collected") or [] if e.get("evidence_id")}
    return any(by_id.get(eid, {}).get("outcome") == "supports" and by_id[eid].get("hypothesis_key") == confirmed
               for eid in root["evidence_ids"])


def _sources(candidates: list[dict]) -> list[str]:
    return [c.get("source") or f"id:{c.get('id')}" for c in candidates or []]


def _record(inc: dict, run: int, result: dict, final: dict | None, env) -> dict:
    gt = inc["ground_truth"]
    from backend.graph.hypotheses import LABEL_KIND

    base = {"id": inc["id"], "run": run, "discrepancy_type": inc["discrepancy_type"],
            "label": {"root_cause": gt["root_cause"], "review": gt["should_require_human_review"],
                      "min_hypotheses": gt["min_hypotheses_needed"],
                      "early_termination_kind": LABEL_KIND.get(gt["early_termination_at"])}}
    incident = result.get("incident")
    if result.get("error") or incident is None or final is None:
        return {**base, "error": result.get("error") or "no final state", "correct": False, "requires_review": True}
    tested = final.get("hypotheses_tested") or []
    critic = [v["verdict"] for v in final.get("critic_verdicts") or []]
    live = env.mode == "live"
    rec = {
        **base,
        "error": None,
        "graph_status": final.get("graph_status"),
        "root_cause_category": final.get("root_cause_category"),
        "correct": final.get("root_cause_category") == gt["root_cause"],
        "hypotheses_tested": tested,
        "deciding_kind": _deciding_kind(tested),
        "graph_confidence": final.get("graph_confidence"),
        "confidence": incident.confidence,
        "requires_review": incident.requires_human_review,
        "review_reasons": incident.review_reasons,
        "judge_decision": incident.judge_decision,
        "revision_count": incident.revision_count,
        "critic": {k: critic.count(k) for k in ("supported", "unsupported", "contradicted")},
        "grounded": _grounded(final),
        "retrieval": {"candidates": _sources(final.get("rag_candidates")),
                      "reranked": _sources(final.get("reranked_candidates"))} if env.real_embeddings else None,
        "llm_calls": len(incident.llm_calls),
        "tokens": incident.total_tokens_used,
        "cost_usd": incident.cost_usd,
        # Wall-clock numbers only mean something against real models.
        "llm_latency_ms": incident.latency_ms if live else None,
        "e2e_latency_ms": incident.e2e_latency_ms if live else None,
    }
    return rec


def _analyze_all(incidents, config, env, runs: int, progress) -> tuple[list[dict], dict[str, dict]]:
    from backend.graph.recon_graph import build_graph
    from backend.main import _analyze_row

    graph = _CapturingGraph(build_graph(config, env.storage))
    records, finals = [], {}
    for run in range(1, runs + 1):
        for i, inc in enumerate(incidents, start=1):
            result = asyncio.run(_analyze_row(benchmark_row(inc), config, graph, env.storage,
                                              bypass_cache=True, session_id=f"eval-run-{run}"))
            records.append(_record(inc, run, result, graph.last, env))
            if run == 1 and graph.last is not None:
                finals[inc["id"]] = graph.last
            progress(f"run {run}/{runs} incident {i}/{len(incidents)} {inc['id']}")
    return records, finals


# ---------------------------------------------------------------------------
# Critic: planted-claim set
# ---------------------------------------------------------------------------
def _planted(finals: dict[str, dict], config, limit: int | None, progress) -> dict:
    from backend.agents.explanation import run_critic
    from backend.evals import planted as P

    per_incident: dict[str, dict] = {}
    outcomes: dict[str, list[dict]] = {k: [] for k in ("clean", *P.DEFECTS)}
    ids = [i for i, f in finals.items() if P.applicable(f)][:limit]
    for n, incident_id in enumerate(ids, start=1):
        state = finals[incident_id]
        drafts = P.drafts(state)
        per_incident[incident_id] = drafts
        for kind, claims in drafts.items():
            if claims is None:
                continue
            out = run_critic(P.critic_state(state, claims), config)
            verdicts = {v["claim_id"]: v for v in out["critic_verdicts"]}
            rejected = [v for v in verdicts.values() if v["verdict"] != "supported"]
            outcomes[kind].append({"incident": incident_id, "critic_status": out["critic_status"],
                                   "rejected": bool(rejected) or out["critic_status"] != "ok",
                                   "stages": sorted({v.get("stage") for v in rejected if v.get("stage")}),
                                   "cost_usd": _cost(out.get("llm_calls") or [])})
        progress(f"planted {n}/{len(ids)} {incident_id}")

    summary = {}
    for kind, items in outcomes.items():
        usable = [o for o in items if o["critic_status"] == "ok"]
        entry = {"drafts": len(items), "critic_unavailable": len(items) - len(usable)}
        if kind == "clean":
            entry["false_rejection"] = M.proportion(o["rejected"] for o in usable)
        else:
            entry["expected_stage"] = P.EXPECTED_STAGE[kind]
            entry["caught"] = M.proportion(o["rejected"] for o in usable)
            entry["caught_by_deterministic"] = M.proportion("deterministic" in o["stages"] for o in usable)
            entry["caught_by_llm"] = M.proportion("llm" in o["stages"] for o in usable)
            entry["missed_incidents"] = [o["incident"] for o in usable if not o["rejected"]]
        summary[kind] = entry
    if outcomes["clean"]:
        summary["clean"]["falsely_rejected_incidents"] = [o["incident"] for o in outcomes["clean"]
                                                          if o["critic_status"] == "ok" and o["rejected"]]
    costs = [o["cost_usd"] for items in outcomes.values() for o in items]
    return {"incidents": len(ids), "draft_set_sha256": P.draft_set_hash(per_incident), "by_draft": summary,
            "cost_usd": round(sum(c for c in costs if c is not None), 6) if None not in costs else None}


def _cost(calls):
    from backend.config import incident_cost

    return incident_cost(calls)[0]


# ---------------------------------------------------------------------------
# Ablations (offline only: graph behavior under changed worlds / ordering)
# ---------------------------------------------------------------------------
@contextlib.contextmanager
def _world(transform):
    from backend.tools import world

    original = dict(world.registry())
    world.set_registry({rid: transform(s) for rid, s in original.items()})
    try:
        yield
    finally:
        world.set_registry(original)


@contextlib.contextmanager
def _delivery_first():
    from backend.graph.hypotheses import CATALOGUE

    original = {k: list(v) for k, v in CATALOGUE.items()}
    for plan in CATALOGUE.values():
        plan.sort(key=lambda h: h.kind != "delivery")  # stable: delivery checks first, rest unchanged
    try:
        yield
    finally:
        CATALOGUE.clear()
        CATALOGUE.update(original)


def _no_confounders(s):
    from dataclasses import replace

    return replace(s, confounders=frozenset())


def _all_confounders(s):
    from dataclasses import replace

    if s.source != "benchmark":
        return s
    extra = set()
    if s.fault != "DELIVERY_GAP":
        extra.add("unrelated_missed_event")
    if s.fault != "APEX_SUPPRESSION":
        extra.add("apex_conditional_dormant")
    return replace(s, confounders=frozenset(s.confounders | extra))


ABLATIONS = {
    "as_built": "the graph and scenario world as committed",
    "no_confounders": "every benchmark record has only its declared fault",
    "all_confounders": "every benchmark record also carries both confounders (where they don't fake its fault)",
    "delivery_first": "the delivery check moved to the front of every plan (the pre-2.0 ordering)",
    "delivery_first_all_confounders": "delivery-first ordering in the all-confounders world",
}


def _ablations(incidents, config, env) -> dict:
    from backend.graph.recon_graph import build_graph
    from backend.models.state import initial_state, review_reasons

    variants = {
        "as_built": contextlib.nullcontext,
        "no_confounders": lambda: _world(_no_confounders),
        "all_confounders": lambda: _world(_all_confounders),
        "delivery_first": _delivery_first,
        "delivery_first_all_confounders": lambda: _stack(_delivery_first(), _world(_all_confounders)),
    }
    out = {}
    for name, ctx in variants.items():
        with ctx():
            graph = build_graph(config, env.storage)
            correct, review, unsafe, confusions = [], [], [], []
            for inc in incidents:
                final = graph.invoke(initial_state(benchmark_row(inc).model_dump(mode="json")))
                ok = final.get("root_cause_category") == inc["ground_truth"]["root_cause"]
                flagged = bool(review_reasons(final))
                correct.append(ok)
                review.append(flagged)
                unsafe.append(not ok and not flagged)
                confusions.append((inc["ground_truth"]["root_cause"], final.get("root_cause_category")))
        out[name] = {"description": ABLATIONS[name], "accuracy": M.proportion(correct),
                     "review_rate": M.proportion(review), "unsafe_auto_clear": M.proportion(unsafe),
                     "confusion": M.confusion(confusions)}
    return out


@contextlib.contextmanager
def _stack(*contexts):
    with contextlib.ExitStack() as stack:
        for c in contexts:
            stack.enter_context(c)
        yield


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def aggregate(records: list[dict], runs: int, retrieval_measured: bool) -> dict:
    first = [r for r in records if r["run"] == 1]
    ok = [r for r in first if not r.get("error")]
    by_type: dict[str, list[bool]] = {}
    for r in first:
        by_type.setdefault(r["discrepancy_type"], []).append(r["correct"])

    metrics = {
        "errors": {"count": len(first) - len(ok), "incidents": [r["id"] for r in first if r.get("error")]},
        "accuracy": {
            "overall": M.proportion(r["correct"] for r in first),
            "by_discrepancy_type": {t: M.proportion(v) for t, v in sorted(by_type.items())},
            "confusion": M.confusion((r["label"]["root_cause"], r.get("root_cause_category")) for r in first),
        },
        "efficiency": {
            "within_min_hypotheses": M.proportion(len(r["hypotheses_tested"]) <= r["label"]["min_hypotheses"] for r in ok),
            "deciding_check_matches_label": M.proportion(r["deciding_kind"] == r["label"]["early_termination_kind"]
                                                        for r in ok if r["correct"]),
            "mean_hypotheses_tested": M.mean(len(r["hypotheses_tested"]) for r in ok),
        },
        "routing": {
            "unsafe_auto_clear": M.proportion(not r["correct"] and not r["requires_review"] for r in first),
            "review_rate": M.proportion(r["requires_review"] for r in first),
            "review_vs_label": M.precision_recall([r["requires_review"] for r in first],
                                                  [r["label"]["review"] for r in first]),
            "calibration_graph_confidence": M.ece([r.get("graph_confidence") for r in ok], [r["correct"] for r in ok]),
            "calibration_final_confidence": M.ece([r.get("confidence") for r in ok], [r["correct"] for r in ok]),
        },
        "explanation": {
            "judge_decisions": dict(sorted(_count(r.get("judge_decision") for r in ok).items())),
            "revised": M.proportion(r.get("revision_count", 0) > 0 for r in ok),
            "grounded_when_accepted": M.proportion(r["grounded"] for r in ok if r.get("grounded") is not None),
        },
        "consistency": _consistency(records) if runs > 1 else None,
        "retrieval": _retrieval(ok) if retrieval_measured else
        {"status": "not_measured", "reason": "needs real embeddings (OPENAI_API_KEY) in live mode"},
        "cost_latency": _cost_latency(ok),
    }
    return metrics


def _count(values):
    out: dict = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return out


def _consistency(records):
    by_incident: dict[str, list[dict]] = {}
    for r in records:
        by_incident.setdefault(r["id"], []).append(r)
    groups = list(by_incident.values())
    return {
        "root_cause_category": M.agreement([[r.get("root_cause_category") for r in g] for g in groups]),
        "review_decision": M.agreement([[r.get("requires_review") for r in g] for g in groups]),
        "judge_decision": M.agreement([[r.get("judge_decision") for r in g] for g in groups]),
    }


def _retrieval(records):
    out = {"status": "measured", "relevance": "same root-cause family (backend/evals/labels.py)"}
    for stage in ("candidates", "reranked"):
        rows = [(r["retrieval"][stage], relevant_sources(r["label"]["root_cause"])) for r in records]
        rows = [(ranked, rel) for ranked, rel in rows if rel]
        out[stage] = {"n": len(rows), **{f"recall@{k}": M.mean(M.recall_at_k(a, b, k) for a, b in rows) for k in (1, 3, 5)},
                      **{f"hit@{k}": M.proportion(M.hit_at_k(a, b, k) for a, b in rows) for k in (1, 3, 5)},
                      "mrr": M.mean(M.reciprocal_rank(a, b) for a, b in rows)}
    return out


def _cost_latency(records):
    costs = [r["cost_usd"] for r in records]
    out = {
        "cost_usd_total": round(sum(costs), 6) if records and None not in costs else None,
        "cost_usd_median": M.percentile(costs, 50) if None not in costs else None,
        "cost_usd_p95": M.percentile(costs, 95) if None not in costs else None,
        "tokens_median": M.percentile([r["tokens"] for r in records], 50),
        "llm_calls_median": M.percentile([r["llm_calls"] for r in records], 50),
    }
    for key in ("e2e_latency_ms", "llm_latency_ms"):
        out[f"{key}_median"] = M.percentile([r[key] for r in records], 50)
        out[f"{key}_p95"] = M.percentile([r[key] for r in records], 95)
    return out


def failure_patterns(records: list[dict]) -> list[dict]:
    groups: dict[tuple, list[str]] = {}
    for r in records:
        if r["run"] != 1:
            continue
        if r.get("error"):
            key = ("error", r["error"][:80])
        elif not r["correct"]:
            key = ("unsafe auto-clear" if not r["requires_review"] else "wrong, sent to review",
                   f"{r['label']['root_cause']} -> {r.get('root_cause_category') or 'none'}")
        elif r.get("judge_decision") == "escalate":
            key = ("correct diagnosis, explanation escalated", ", ".join(r.get("review_reasons") or []))
        else:
            continue
        groups.setdefault(key, []).append(r["id"])
    return [{"kind": k[0], "detail": k[1], "count": len(v), "incidents": v}
            for k, v in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))]


# ---------------------------------------------------------------------------
# Cost estimate (printed before a live run)
# ---------------------------------------------------------------------------
# Rough per-call token assumptions from earlier live checks; the estimate is padded 1.5x.
_EST = {"proposer": (3200, 700), "critic": (3000, 400), "reranker": (900, 20)}
_REVISION_RATE = 0.4


def estimate_cost(config_key: str, n: int, runs: int, planted_incidents: int) -> float | None:
    from backend.config import CONFIGS, call_cost_usd

    cfg = CONFIGS[config_key]

    def c(model, kind):
        return call_cost_usd({"model": model, "input_tokens": _EST[kind][0], "output_tokens": _EST[kind][1]})

    parts = [c(cfg.synthesis_llm, "proposer"), c(cfg.critic_llm, "critic"), c(cfg.reranker_llm, "reranker")]
    if None in parts:
        return None
    per_incident = parts[2] + (parts[0] + parts[1]) * (1 + _REVISION_RATE)
    planted = planted_incidents * 7 * parts[1]
    return round(1.5 * (per_incident * n * runs + planted), 2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return None


def run_eval(mode: str = "offline", config_key: str = "claude", runs: int = 1, limit: int | None = None,
             planted_limit: int | None = None, yes: bool = False, ablations: bool | None = None,
             progress=lambda msg: None) -> dict:
    from backend.config import CONFIGS, PRICING_PER_MTOK
    from backend.graph.hypotheses import GRAPH_VERSION
    from backend.prompts import recorded_versions
    from backend.seed.fsc_incidents import seed_artifacts

    incidents = load_incidents()[:limit]
    config = CONFIGS[config_key]
    ablations = (mode == "offline") if ablations is None else ablations
    with environment(mode, config_key, yes) as env:
        asyncio.run(seed_artifacts(env.storage))
        records, finals = _analyze_all(incidents, config, env, runs, progress)
        planted = _planted(finals, config, planted_limit, progress)
        ablation_results = _ablations(incidents, config, env) if ablations else None
        notes = env.notes
        real_embeddings = env.real_embeddings

    models = sorted({config.ingestion_llm, config.reranker_llm, config.synthesis_llm, config.critic_llm})
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "config": config_key,
        "models": models,
        "runs": runs,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
        "dataset": {"path": "data/benchmark_ground_truth.json", "sha256": sha256_file(GROUND_TRUTH),
                    "scenarios_sha256": sha256_file(SCENARIOS), "incidents": len(incidents)},
        "graph_version": GRAPH_VERSION,
        "prompt_versions": recorded_versions(),
        "pricing_per_mtok": {m: list(PRICING_PER_MTOK[m]) for m in models if m in PRICING_PER_MTOK},
        "caveats": CAVEATS + ([OFFLINE_CAVEAT] if mode == "offline" else []),
        "environment_notes": notes,
        "metrics": aggregate(records, runs, real_embeddings),
        "critic_planted": planted,
        "ablations": ablation_results,
        "failure_patterns": failure_patterns(records),
        "incidents": records,
    }


def write_results(results: dict, out_dir: Path = RESULTS_DIR) -> tuple[Path, Path]:
    from backend.evals.report import render
    from backend.evals.schema import EvalResults

    EvalResults.model_validate(results)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{results['mode']}_{results['config']}"
    json_path, md_path = out_dir / f"{stem}.json", out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(results, indent=2, sort_keys=False) + "\n")
    md_path.write_text(render(results))
    return json_path, md_path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["offline", "live"], default="offline")
    p.add_argument("--config", choices=["claude", "groq", "hybrid"], default="claude")
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--limit", type=int, default=None, help="only the first N incidents")
    p.add_argument("--planted-limit", type=int, default=None, help="planted-claim drafts for the first N incidents")
    p.add_argument("--out", type=Path, default=RESULTS_DIR)
    p.add_argument("--yes", action="store_true", help="confirm spending money on a live run")
    args = p.parse_args(argv)

    n = len(load_incidents()[:args.limit])
    if args.mode == "live":
        estimate = estimate_cost(args.config, n, args.runs, min(n, args.planted_limit or n))
        print(f"Estimated cost: ${estimate} (padded 1.5x; unknown model price -> None)", file=sys.stderr)
    try:
        results = run_eval(args.mode, args.config, args.runs, args.limit, args.planted_limit, args.yes,
                           progress=lambda m: print(m, file=sys.stderr))
    except LiveRunRefused as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2
    json_path, md_path = write_results(results, args.out)
    if args.out.resolve() == RESULTS_DIR.resolve():
        from backend.evals.publish import publish

        publish()
    total = results["metrics"]["cost_latency"]["cost_usd_total"]
    planted_cost = results["critic_planted"]["cost_usd"]
    if args.mode == "live":
        print(f"Measured cost: incidents ${total}, planted-claim critic ${planted_cost}", file=sys.stderr)
    print(f"Wrote {json_path.relative_to(ROOT) if json_path.is_relative_to(ROOT) else json_path} and {md_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
