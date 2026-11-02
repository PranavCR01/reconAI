"""The /hypotheses page shows exactly the catalogue the graph runs."""
from backend.graph.hypotheses import CATALOGUE, CONFIRMED_WHEN, REVIEW_THRESHOLD, TOOL_DESCRIPTION, catalogue_summary
from backend.graph.publish import PUBLISHED, render


def test_published_catalogue_is_current():
    assert PUBLISHED.read_text() == render(), "run `python -m backend.graph.publish` and commit the result"


def test_every_hypothesis_is_described_in_order():
    summary = catalogue_summary()
    assert [t["type"] for t in summary["discrepancy_types"]] == list(CATALOGUE)
    for t in summary["discrepancy_types"]:
        plan = CATALOGUE[t["type"]]
        assert [h["id"] for h in t["hypotheses"]] == [h.id for h in plan], "page order must be check order"
        for shown, h in zip(t["hypotheses"], plan):
            assert shown["confidence"] == h.confidence
            assert shown["goes_to_review"] == (h.confidence < REVIEW_THRESHOLD)
    assert {h.kind for p in CATALOGUE.values() for h in p} <= set(CONFIRMED_WHEN)
    assert {h.tool for p in CATALOGUE.values() for h in p} <= set(TOOL_DESCRIPTION)


def test_review_threshold_is_the_one_the_graph_uses():
    import backend.agents.hypothesis as agent

    assert agent.REVIEW_THRESHOLD is REVIEW_THRESHOLD == 0.75
