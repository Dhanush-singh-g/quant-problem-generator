"""Final publication boundary for model-generated and curated CS questions."""
import math
from decimal import Decimal
from core.model_registry import model_spec
from core.formula_engine import solve
from core.cs_question_engine import PATTERNS, fact_by_id
from agents.solver_agent_a import solve_a
from agents.solver_agent_b import solve_b
from agents.validator_agent import validate_answers
from agents.cs_validator import validate_cs_question
from services.question_designer import CONTEXTS


def validate_model_question(q):
    meta = q.get("generation_metadata", {})
    stem = meta.get("canonical_stem", q.get("story_text", ""))
    if meta.get("question_family") == "computer_science":
        result = validate_cs_question(q)
        domain, fact = fact_by_id(meta.get("fact_id"))
        if result["final_validation"] != "valid":
            raise ValueError(result["reasoning"])
        if stem not in {pattern.format(skill=fact["skill"]) for pattern in PATTERNS[fact["difficulty"]]}:
            raise ValueError("CS stem differs from reviewed question patterns")
        if q["canonical_solution"] != f"{fact['correct_answer']} {fact['fact']}":
            raise ValueError("CS explanation differs from reviewed fact")
        verification = {"mode": "deterministic_fact_bank", "validator": result}
    else:
        domain, spec = model_spec(meta.get("template_used"))
        if q["domain"] != domain or q["difficulty"] != spec["difficulty"]:
            raise ValueError("Model topic/difficulty mismatch")
        variables = q["variables"]
        if set(variables) != set(spec["variables"]):
            raise ValueError("Model parameter set mismatch")
        for name, rule in spec["variables"].items():
            value = variables[name]
            if rule.get("type") == "text":
                if value not in rule["values"]:
                    raise ValueError("Unreviewed text parameter")
            else:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("Invalid numeric parameter")
                if not rule["min"] <= value <= rule["max"]:
                    raise ValueError("Parameter outside model range")
                if rule.get("type") == "int" and int(value) != value:
                    raise ValueError("Integer parameter required")
                if rule.get("step"):
                    steps = (value - rule["min"]) / rule["step"]
                    if abs(steps - round(steps)) > 1e-6:
                        raise ValueError("Parameter outside model step grid")
        if stem != spec["story_template"].format(**variables):
            raise ValueError("Canonical story was altered")
        answer, unit, solution = solve(spec["template_id"], variables)
        if unit == "ratio":
            answer_matches = str(q["answer_value"]) == str(answer)
        else:
            answer_matches = Decimal(str(q["answer_value"])) == Decimal(str(answer))
        if not answer_matches or q["answer_unit"] != unit:
            raise ValueError("Answer or unit differs from canonical model")
        if q["canonical_solution"] != solution:
            raise ValueError("Canonical solution was altered")
        result = validate_answers(q, solve_a(q), solve_b(q))
        if result["final_validation"] != "valid":
            raise ValueError("Independent answer, unit, or option validation failed")
        verification = {"mode": "reviewed_model_independent_solver", "validator": result}
    context_id = meta.get("context_id")
    expected_story = f"Context: {CONTEXTS[context_id]}\n\n{stem}" if context_id in CONTEXTS else stem
    if q["story_text"] != expected_story:
        raise ValueError("Unreviewed presentation text")
    return verification
