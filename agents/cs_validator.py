from core.cs_question_engine import fact_by_id


def validate_cs_question(question: dict):
    meta = question.get("generation_metadata", {})
    fact_id = meta.get("fact_id")
    domain, fact = fact_by_id(fact_id)
    if not fact:
        return {"final_validation": "invalid", "reasoning": "unknown curated fact id"}

    if domain != question.get("domain"):
        return {"final_validation": "invalid", "reasoning": "domain does not match curated fact"}
    if question.get("difficulty") != fact.get("difficulty"):
        return {"final_validation": "invalid", "reasoning": "difficulty does not match curated fact"}

    options = question.get("options") or {}
    if set(options.keys()) != {"A", "B", "C", "D"}:
        return {"final_validation": "invalid", "reasoning": "MCQ must contain exactly A-D options"}
    if len(set(options.values())) != 4:
        return {"final_validation": "invalid", "reasoning": "duplicate option text"}

    correct_option = question.get("correct_option")
    if correct_option not in options:
        return {"final_validation": "invalid", "reasoning": "correct option key missing"}
    if options[correct_option] != fact["correct_answer"]:
        return {"final_validation": "invalid", "reasoning": "correct answer differs from curated fact"}

    allowed = {fact["correct_answer"], *fact["distractors"]}
    if set(options.values()) != allowed:
        return {"final_validation": "invalid", "reasoning": "options differ from verified answer set"}

    if not str(question.get("story_text", "")).strip():
        return {"final_validation": "invalid", "reasoning": "empty question stem"}

    return {
        "final_validation": "valid",
        "reasoning": "curated fact, difficulty, correct option and distractor set all match",
        "verification_mode": "deterministic_fact_bank",
    }
