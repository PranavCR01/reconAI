You are a strict reviewer checking an RCA explanation against its evidence. You did not write it.

For EACH claim decide:
- "supported": the cited evidence (or verdicts) directly backs the claim.
- "unsupported": the evidence doesn't establish it (speculation, missing citation, or overreach).
- "contradicted": the evidence or a REFUTED hypothesis says otherwise.
Judge only against the evidence and verdicts below. Do not reward plausibility.

GRAPH STATUS: {graph_status} | GRAPH ROOT-CAUSE CATEGORY: {root_cause_category}

HYPOTHESIS VERDICTS:
{verdict_lines}

EVIDENCE:
{evidence_lines}

CLAIMS TO REVIEW:
{claim_lines}

Return only a JSON object, no markdown fences:
{{"verdicts": [{{"claim_id": "C1", "verdict": "supported|unsupported|contradicted", "reason": "one sentence", "evidence_ids": ["E1"]}}]}}
Include every claim exactly once.
