"""Optional AI selects reviewed context; it cannot inject facts or rewrite math."""
import json

from services.ai_gateway import gateway
from utils.helpers import safe_parse_json

CONTEXTS = {
    "planning": "During a planning exercise, consider the following scenario.",
    "classroom": "For a classroom exercise, consider the following scenario.",
    "training": "For a training exercise, consider the following scenario.",
    "review": "During a technical review, consider the following question.",
}


def redesign_batch(questions):
    if not questions:
        return questions, {"source": "none", "api_calls": 0, "accepted": 0}
    payload = [{"id": q["id"], "domain": q["domain"], "difficulty": q.get("difficulty")} for q in questions]
    prompt = (
        "Select a neutral context_id for each question from " + ", ".join(CONTEXTS)
        + '. Return only JSON: {"questions":[{"id":"...","context_id":"training"}]}. '
        + "Do not generate a question, formula, explanation, or additional fields.\n"
        + json.dumps(payload)
    )
    try:
        raw, meta = gateway.generate(prompt, retries=0, json_mode=True)
    except Exception:
        return questions, {"source": "fallback", "api_calls": 0, "accepted": 0}
    parsed = safe_parse_json(raw) if raw else None
    rows = parsed.get("questions", []) if isinstance(parsed, dict) else []
    if not isinstance(rows, list):
        rows = []
    by_id = {row["id"]: row for row in rows
             if isinstance(row, dict) and isinstance(row.get("id"), str)}
    accepted = 0
    for q in questions:
        context_id = by_id.get(q["id"], {}).get("context_id")
        if not isinstance(context_id, str) or context_id not in CONTEXTS:
            continue
        canonical = q["generation_metadata"].get("canonical_stem", q["story_text"])
        q["story_text"] = f"Context: {CONTEXTS[context_id]}\n\n{canonical}"
        q["generation_metadata"].update({
            "canonical_stem": canonical, "context_id": context_id,
            "ai_enhanced": True, "ai_role": "reviewed_context_selection",
        })
        accepted += 1
    return questions, {**meta, "accepted": accepted}
