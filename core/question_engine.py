import random
import uuid
from core.formula_engine import solve

LETTERS = ["A", "B", "C", "D"]


def _sample(spec):
    if spec.get("type") == "text":
        return random.choice(spec.get("values", ["A", "B"]))
    mn, mx = spec.get("min", 1), spec.get("max", 20)
    step = spec.get("step")
    if spec.get("type") == "float":
        if step:
            n = int(round((mx - mn) / step))
            return round(mn + random.randint(0, n) * step, 4)
        return round(random.uniform(mn, mx), 2)
    if step:
        vals = list(range(int(mn), int(mx) + 1, int(step)))
        return random.choice(vals)
    return random.randint(int(mn), int(mx))


def _format(value, unit):
    if unit == "ratio":
        return str(value)
    if unit == "%":
        return f"{value}%"
    return f"{value} {unit}".strip()


def _num(value):
    value = float(value)
    return int(round(value)) if abs(value - round(value)) < 1e-9 else round(value, 2)


def _candidate_wrong_values(template_id, v, answer):
    """Generate plausible mistakes tied to the mathematical structure."""
    out = []
    try:
        if template_id == "TSD_H_002_MeetAfterPause":
            combined = v["speed_a"] + v["speed_b"]
            # Ignore A's pause, or wrongly assume both actors stop during it.
            out += [v["separation"] / combined,
                    v["pause_hours"] + v["separation"] / combined]
        elif template_id == "WT_H_002_WorkerJoins":
            combined_time = v["a_days"] * v["b_days"] / (v["a_days"] + v["b_days"])
            # Treat both workers as present from the start, or discard A's progress.
            out += [combined_time, v["alone_days"] + combined_time]
        elif template_id == "PC_H_002_DelayedOutlet":
            inlet_rate = 1 / v["inlet_a_hours"] + 1 / v["inlet_b_hours"]
            net_rate = inlet_rate - 1 / v["outlet_hours"]
            # Open the outlet from the start, or ignore it entirely.
            out += [1 / net_rate, 1 / inlet_rate]
        elif template_id == "TSD_M_001_RelativeSpeedMeeting":
            diff = abs(v["speed1"] - v["speed2"])
            if diff:
                out.append(v["distance_apart"] / diff)
            out.append(v["distance_apart"] / v["speed1"])
        elif template_id == "TSD_H_001_TrainCrossPlatform":
            speed_mps = v["speed"] * 5 / 18
            out += [v["train_length"] / speed_mps, (v["train_length"] + v["platform_length"]) / v["speed"]]
        elif template_id == "WT_E_001_WorkCompletedPercent":
            out += [(v["total_time"] - v["days_worked"]) / v["total_time"] * 100, v["days_worked"] * 100]
        elif template_id == "WT_M_001_CombinedWorkTwoPeople":
            a, b = v["person1_time"], v["person2_time"]
            out += [(a + b) / 2, min(a, b), a + b]
        elif template_id == "WT_H_001_JoinLeave":
            a, b, t = v["person1_time"], v["person2_time"], v["together_days"]
            out += [a * b / (a + b), t + b, b]
        elif template_id == "PC_E_001_SingleInletPercent":
            out += [(v["fill_time"] - v["open_hours"]) / v["fill_time"] * 100, v["open_hours"] * 100]
        elif template_id == "PC_M_001_TwoInlets":
            a, b = v["pipe1_fill_time"], v["pipe2_fill_time"]
            out += [(a + b) / 2, min(a, b), a + b]
        elif template_id == "PC_H_001_TwoInletsOutlet":
            a, b, c = v["pipe1_fill_time"], v["pipe2_fill_time"], v["outlet_time"]
            out += [1 / (1 / a + 1 / b), 1 / (1 / a + 1 / b + 1 / c), c]
        elif template_id == "PLD_M_001_SuccessiveDiscount":
            mp, d1, d2 = v["marked_price"], v["discount1"], v["discount2"]
            out += [mp * (1 - (d1 + d2) / 100), mp * (1 - d1 / 100), mp * (1 - d2 / 100)]
        elif template_id == "PLD_H_001_MarkupSuccessiveDiscountProfit":
            cp, m, d1, d2 = v["cost_price"], v["markup"], v["discount1"], v["discount2"]
            sp_one = cp * (1 + m / 100) * (1 - d1 / 100)
            sp_add = cp * (1 + m / 100) * (1 - (d1 + d2) / 100)
            out += [abs((sp_one - cp) / cp * 100), abs((sp_add - cp) / cp * 100), m - d1 - d2]
        elif template_id == "MR_E_001_ComponentQuantity":
            a, b, total = v["ratio1"], v["ratio2"], v["total_quantity"]
            out += [total * b / (a + b), total * a / b]
        elif template_id == "MR_M_001_RatioAdjustment":
            out += [v["added_quantity"] * (v["initial_ratio_part1"] + v["initial_ratio_part2"]), v["added_quantity"]]
        elif template_id == "MR_H_001_RepeatedReplacement":
            total, removed, n = v["vessel_capacity"], v["replaced_quantity"], v["repetitions"]
            out += [max(0, total - removed * n), total * (1 - removed / total), total - removed]
        elif template_id == "ABP_E_001_FutureAge":
            out += [v["current_age"] - v["years_future"], v["years_future"]]
        elif template_id == "ABP_H_001_DifferenceFutureMultiple":
            d, years, multiple = v["age_difference"], v["years_future"], v["future_multiple"]
            out += [d / (multiple - 1), d - years, d / multiple]
    except (ZeroDivisionError, ValueError, TypeError):
        pass

    cleaned = []
    for x in out:
        try:
            if isinstance(answer, str):
                continue
            x = _num(x)
            if x > 0 and x != answer and x not in cleaned:
                cleaned.append(x)
        except (ValueError, TypeError):
            continue
    return cleaned


def _distractors(template_id, answer, unit, variables):
    if unit == "ratio":
        a, b = map(int, str(answer).split(":"))
        vals = [f"{b}:{a}", f"{a + 1}:{b}", f"{a}:{b + 1}"]
    else:
        wrong = _candidate_wrong_values(template_id, variables, answer)
        x = float(answer)
        delta = max(1, abs(x) * 0.1)
        generic = [_num(x + delta), _num(max(0.01, x - delta)), _num(x * 2 if x else 1)]
        raw = wrong + generic
        vals = []
        for z in raw:
            formatted = _format(z, unit)
            if formatted not in vals and formatted != _format(answer, unit):
                vals.append(formatted)
            if len(vals) == 3:
                break

    correct = _format(answer, unit)
    unique = [correct]
    for x in vals:
        if x not in unique:
            unique.append(x)
    while len(unique) < 4:
        if unit == "ratio":
            candidate = f"{len(unique) + 2}:{len(unique) + 1}"
        else:
            candidate = _format(_num(float(answer) + len(unique) * 3.7), unit)
        if candidate not in unique:
            unique.append(candidate)

    random.shuffle(unique)
    options = dict(zip(LETTERS, unique[:4]))
    return options, next(k for k, value in options.items() if value == correct)


def build_question(domain, template, max_attempts=50):
    for _ in range(max_attempts):
        v = {k: _sample(s) for k, s in template.get("variables", {}).items()}
        if "item1_name" in v and "item2_name" in v and v["item1_name"] == v["item2_name"]:
            continue
        try:
            answer, unit, derivation = solve(template.get("template_id", ""), v)
            story = template["story_template"].format(**v)
            opts, corr = _distractors(template.get("template_id", ""), answer, unit, v)
            return {
                "id": str(uuid.uuid4()),
                "domain": domain,
                "story_text": story,
                "options": opts,
                "correct_option": corr,
                "canonical_solution": derivation,
                "answer_value": answer,
                "answer_unit": unit,
                "variables": v,
                "generation_metadata": {
                    "question_family": "quantitative",
                    "template_used": template.get("template_id", "unknown"),
                    "template_difficulty": template.get("difficulty", "medium"),
                    "subdomain": template.get("subdomain", "general"),
                    "variables_used": v,
                    "method": "difficulty_specific_deterministic_template",
                },
            }
        except (ValueError, ZeroDivisionError):
            continue
    raise RuntimeError(f"Could not produce a valid question for {domain} / {template.get('difficulty', 'unknown')}")
