"""Markdown report for an eval results file."""
from __future__ import annotations


def _pct(rate: dict | None) -> str:
    if not rate or rate.get("rate") is None:
        return "n/a"
    lo, hi = rate["ci95"]
    return f"{rate['rate'] * 100:.0f}% ({rate['k']}/{rate['n']}; 95% CI {lo * 100:.0f}-{hi * 100:.0f}%)"


def _num(v, fmt="{:.4f}") -> str:
    return "n/a" if v is None else fmt.format(v)


def render(r: dict) -> str:
    m = r["metrics"]
    lines = [
        f"# Eval report: {r['mode']} / {r['config']}",
        "",
        f"- Models: {', '.join(r['models'])}",
        f"- Runs: {r['runs']}, incidents: {r['dataset']['incidents']}, graph {r['graph_version']}, "
        f"dataset sha256 `{r['dataset']['sha256'][:12]}`, scenarios `{r['dataset']['scenarios_sha256'][:12]}`",
        f"- Prompts: {', '.join(f'{k} `{v}`' for k, v in r['prompt_versions'].items())}",
        "",
        "## Read this first",
        "",
        *[f"- {c}" for c in r["caveats"]],
        *[f"- {n}" for n in r["environment_notes"]],
        "",
        "## Diagnosis (hypothesis graph)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Root-cause accuracy | {_pct(m['accuracy']['overall'])} |",
        *[f"| &nbsp;&nbsp;{t} | {_pct(v)} |" for t, v in m["accuracy"]["by_discrepancy_type"].items()],
        f"| Within labeled minimum checks | {_pct(m['efficiency']['within_min_hypotheses'])} |",
        f"| Deciding check matches label (correct only) | {_pct(m['efficiency']['deciding_check_matches_label'])} |",
        f"| Mean checks run | {_num(m['efficiency']['mean_hypotheses_tested'], '{:.2f}')} |",
        f"| Errors | {m['errors']['count']} |",
        "",
        "## Safety routing",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| **Unsafe auto-clear** (wrong and not sent to review) | {_pct(m['routing']['unsafe_auto_clear'])} |",
        f"| Sent to review | {_pct(m['routing']['review_rate'])} |",
        f"| Review precision vs labels | {_pct(m['routing']['review_vs_label']['precision'])} |",
        f"| Review recall vs labels | {_pct(m['routing']['review_vs_label']['recall'])} |",
        f"| ECE, graph confidence | {_num(m['routing']['calibration_graph_confidence']['ece'])} |",
        f"| ECE, final confidence | {_num(m['routing']['calibration_final_confidence']['ece'])} |",
        "",
        "Review labels (`should_require_human_review`) were written for the original design; disagreement "
        "with them is reported, not optimized for.",
        "",
        "## Explanation (proposer / critic / judge)",
        "",
        f"- Judge decisions: {m['explanation']['judge_decisions']}",
        f"- Revised once: {_pct(m['explanation']['revised'])}",
        f"- Grounded when accepted: {_pct(m['explanation']['grounded_when_accepted'])}",
        "",
        "### Critic on planted claims",
        "",
        f"{r['critic_planted']['incidents']} incidents; draft set sha256 `{r['critic_planted']['draft_set_sha256'][:12]}`.",
        "",
        "| Draft | Expected stage | Caught | By deterministic | By LLM | Critic unavailable |",
        "|---|---|---|---|---|---|",
    ]
    for kind, e in r["critic_planted"]["by_draft"].items():
        if kind == "clean":
            lines.append(f"| clean (false rejection) | - | {_pct(e['false_rejection'])} | - | - | {e['critic_unavailable']} |")
        else:
            lines.append(f"| {kind} | {e['expected_stage']} | {_pct(e['caught'])} | {_pct(e['caught_by_deterministic'])} "
                         f"| {_pct(e['caught_by_llm'])} | {e['critic_unavailable']} |")

    c = m["consistency"]
    lines += ["", "## Consistency across runs", ""]
    lines += ["Single run; not measured."] if not c else [f"- {k}: {_pct(v)}" for k, v in c.items()]

    ret = m["retrieval"]
    lines += ["", "## Retrieval", ""]
    if ret.get("status") != "measured":
        lines.append(f"Not measured: {ret.get('reason')}.")
    else:
        lines.append(f"Relevance: {ret['relevance']}.")
        lines += ["", "| Stage | n | recall@1 | recall@3 | recall@5 | hit@5 | MRR |", "|---|---|---|---|---|---|---|"]
        for stage in ("candidates", "reranked"):
            s = ret[stage]
            lines.append(f"| {stage} | {s['n']} | {_num(s['recall@1'])} | {_num(s['recall@3'])} | {_num(s['recall@5'])} "
                         f"| {_pct(s['hit@5'])} | {_num(s['mrr'])} |")

    cl = m["cost_latency"]
    lines += ["", "## Cost and latency (per incident)", "",
              f"- Cost: median {_num(cl['cost_usd_median'], '${:.4f}')}, p95 {_num(cl['cost_usd_p95'], '${:.4f}')}, "
              f"total {_num(cl['cost_usd_total'], '${:.4f}')}; planted-claim critic {_num(r['critic_planted']['cost_usd'], '${:.4f}')}",
              f"- Tokens: median {cl['tokens_median']}; LLM calls: median {cl['llm_calls_median']}",
              f"- End-to-end: median {_num(cl['e2e_latency_ms_median'], '{:.0f} ms')}, p95 {_num(cl['e2e_latency_ms_p95'], '{:.0f} ms')}; "
              f"LLM time: median {_num(cl['llm_latency_ms_median'], '{:.0f} ms')}"]

    if r.get("ablations"):
        lines += ["", "## Ablations (graph only)", "", "| Variant | Accuracy | Sent to review | Unsafe auto-clear |",
                  "|---|---|---|---|"]
        for name, a in r["ablations"].items():
            lines.append(f"| {name}: {a['description']} | {_pct(a['accuracy'])} | {_pct(a['review_rate'])} "
                         f"| {_pct(a['unsafe_auto_clear'])} |")

    lines += ["", "## Failure patterns", ""]
    if not r["failure_patterns"]:
        lines.append("None.")
    for f in r["failure_patterns"]:
        lines.append(f"- **{f['kind']}** ({f['detail']}): {f['count']}: {', '.join(f['incidents'])}")
    return "\n".join(lines) + "\n"
