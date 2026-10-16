"""Deterministic difficulty classifier; no LLM call.

Quantitative difficulty comes from the curated template family, not from an
arbitrary label added by the assessment request. CS difficulty comes from the
curated fact bank.
"""


def classify_difficulty(q):
    meta = q.get("generation_metadata", {})
    template_band = meta.get("template_difficulty")
    if template_band in {"easy", "medium", "hard"}:
        return {
            "difficulty": template_band,
            "reason": f"curated {template_band} quantitative structure ({meta.get('subdomain', 'general')})",
        }

    declared = meta.get("declared_difficulty")
    if declared in {"easy", "medium", "hard"}:
        return {"difficulty": declared, "reason": "curated CS fact-bank difficulty"}

    return {"difficulty": "medium", "reason": "unclassified legacy question"}
