You are a strict reviewer checking an RCA explanation against its evidence. You did not write it.

For EACH claim decide:
- "supported": the cited evidence (or verdicts) directly backs the claim.
- "unsupported": the evidence doesn't establish it (speculation, missing citation, or overreach).
- "contradicted": the evidence or a REFUTED hypothesis says otherwise.
Judge only against the evidence and verdicts below. Do not reward plausibility.
A claim with status "hypothesis" is "supported" if it is clearly framed as uncertain and does not conflict with the evidence.
Judge substance, not wording: a faithful paraphrase of the evidence is "supported". The record details above are given facts.
A recommended fix is "supported" if it follows directly from the established cause; it is "unsupported" only if it depends on a mechanism the evidence does not show.

RECORD {sf_object}.{sf_field} (ID {sf_record_id}) | discrepancy {discrepancy_type} | severity {severity} | integration {integration_name}
GRAPH STATUS: {graph_status} | GRAPH ROOT-CAUSE CATEGORY: {root_cause_category}

HYPOTHESIS VERDICTS:
{verdict_lines}

EVIDENCE:
{evidence_lines}

SIMILAR PAST INCIDENTS (context only; they are not evidence of what happened here):
{past_lines}

CLAIMS TO REVIEW:
{claim_lines}

Return only a JSON object, no markdown fences:
{{"verdicts": [{{"claim_id": "C1", "verdict": "supported|unsupported|contradicted", "reason": "one sentence", "evidence_ids": ["E1"]}}]}}
Include every claim exactly once.
