"""Similar-incident retrieval searches by the confirmed cause, not just by object and field."""
import asyncio


from backend.config import AgentConfig
from backend.graph.recon_graph import build_graph
from backend.models.state import initial_state
from backend.tests.helpers import ground_truth_row
from backend.tools.rag_tools import CATEGORY_TERMS, retrieval_query

CONFIG = AgentConfig()


def _run(graph, row):
    return graph.invoke(initial_state(row.model_dump(mode="json")))


def test_query_names_the_confirmed_cause():
    state = {"recon_row": {"sf_object": "Contact", "sf_field": "Phone", "discrepancy_type": "NULL_DOWNSTREAM"},
             "graph_status": "confirmed", "root_cause_category": "FLS_STRIPPED",
             "hypothesis_verdicts": [{"hypothesis_id": "H1", "label": "cleared downstream", "verdict": "refuted"},
                                     {"hypothesis_id": "H3a", "label": "can't read the field (FLS)", "verdict": "confirmed"}]}
    q = retrieval_query(state)
    assert "Contact" in q and "Phone" in q and CATEGORY_TERMS["FLS_STRIPPED"] in q and "can't read the field" in q
    assert "cleared downstream" not in q and "H1" not in q, "refuted hypotheses must not steer retrieval"


def test_unconfirmed_query_says_nothing_about_hypotheses():
    state = {"recon_row": {"sf_object": "Address__c", "sf_field": "PostalCode", "discrepancy_type": "STALE_VALUE"},
             "graph_status": "exhausted", "root_cause_category": None, "hypotheses_tested": ["HSV1", "HSV2"],
             "hypothesis_verdicts": [{"hypothesis_id": "HSV1", "label": "CDC excluded", "verdict": "refuted"}]}
    assert retrieval_query(state) == "Address__c PostalCode STALE_VALUE"


def test_every_category_has_search_terms():
    from backend.graph.hypotheses import CATEGORIES

    assert set(CATEGORIES) <= set(CATEGORY_TERMS)


def test_cause_aware_query_retrieves_the_right_kind_of_incident(storage, ground_truth):
    """With the (topic-weighted fake) embeddings, the old object/field/hypothesis-ID query put a
    same-cause incident first for 3/50 benchmark incidents; naming the cause gets 43/50. This shows
    the query carries the cause; real-embedding retrieval quality is measured by the live evals."""
    from backend.evals.labels import relevant_sources
    from backend.seed.fsc_incidents import seed_artifacts
    from backend.tools.rag_tools import embed_text

    asyncio.run(seed_artifacts(storage))
    graph = build_graph(CONFIG, storage)
    hit1 = hit5 = 0
    for inc in ground_truth:
        final = _run(graph, ground_truth_row(inc))
        sources = [c["source"] for c in storage.search_artifacts_sync(embed_text(retrieval_query(final)), limit=8)]
        relevant = relevant_sources(inc["ground_truth"]["root_cause"])
        hit1 += bool(sources[:1] and sources[0] in relevant)
        hit5 += bool(set(sources[:5]) & relevant)
    assert hit1 >= 40 and hit5 >= 45, (hit1, hit5)
