from core.formula_engine import equivalent
from core.verification_engine import verify_solve


def solve_b(q):
    tid = q.get("generation_metadata", {}).get("template_used", "")
    v = q.get("variables") or q.get("generation_metadata", {}).get("variables_used", {})
    try:
        ans, unit = verify_solve(tid, v)
        expected = q.get("answer_value", ans)
        ok = equivalent(ans, expected)
        text = str(ans) if unit == "ratio" else f"{ans} {unit}"
        return {
            "method": "independent verification engine",
            "steps": "Recomputed from source variables using a separate formula implementation and compared with the canonical answer.",
            "answer": text,
            "answer_value": ans,
            "unit": unit,
            "confidence": 1.0 if ok else 0.0,
        }
    except Exception as e:
        return {"method": "verification_failed", "steps": str(e), "answer": "", "confidence": 0.0}
