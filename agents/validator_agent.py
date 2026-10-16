from core.formula_engine import equivalent


def _format(value, unit):
    if unit == "ratio":
        return str(value).strip()
    if unit == "%":
        return f"{value}%"
    return f"{value} {unit}".strip()


def validate_answers(generator_json, solver_a_json, solver_b_json):
    expected = generator_json.get("answer_value")
    a = solver_a_json.get("answer_value")
    b = solver_b_json.get("answer_value")
    ma = equivalent(expected, a)
    mb = equivalent(expected, b)

    options = generator_json.get("options", {})
    correct_key = generator_json.get("correct_option")
    option = str(options.get(correct_key, "")).strip().lower()
    expected_option = _format(expected, generator_json.get("answer_unit", "")).strip().lower()
    option_ok = option == expected_option

    unit = generator_json.get("answer_unit", "")
    units_ok = solver_a_json.get("unit") == unit == solver_b_json.get("unit")
    unique_options = len(set(options.values())) == 4
    valid = (ma and mb and option_ok and units_ok and unique_options
             and set(options) == {"A", "B", "C", "D"} and correct_key in options
             and solver_a_json.get("confidence", 0) > 0 and solver_b_json.get("confidence", 0) > 0)
    return {
        "match_A": ma,
        "match_B": mb,
        "option_consistent": option_ok,
        "units_consistent": units_ok,
        "unique_options": unique_options,
        "final_validation": "valid" if valid else "invalid",
        "reasoning": "independent deterministic consensus passed" if valid else "deterministic validation mismatch",
    }
