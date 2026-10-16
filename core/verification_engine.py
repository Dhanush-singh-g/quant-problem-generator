"""Independent deterministic recomputation for quantitative verification.

This module intentionally does not call formula_engine.solve. It duplicates the
mathematics using a separate implementation so solver B can catch accidental
regressions in the canonical formula engine.
"""
import math
from decimal import Decimal, ROUND_HALF_UP


def _round(x):
    if isinstance(x, Decimal):
        if x == x.to_integral_value():
            return int(x)
        return float(x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    x = float(x)
    return int(round(x)) if abs(x - round(x)) < 1e-9 else round(x, 2)


def verify_solve(template_id: str, v: dict):
    # Independently derive elapsed time from conservation; do not reuse the ledger solver.
    if template_id == "TSD_H_002_MeetAfterPause":
        moving_rate = float(v["speed_a"] + v["speed_b"])
        covered = moving_rate * v["initial_hours"] + v["speed_b"] * v["pause_hours"]
        if covered >= v["separation"]:
            raise ValueError("Meeting must occur after the pause")
        return _round((v["separation"] + v["speed_a"] * v["pause_hours"]) / moving_rate), "hours"
    if template_id == "WT_H_002_WorkerJoins":
        a, b, first = float(v["a_days"]), float(v["b_days"]), float(v["alone_days"])
        if first >= a:
            raise ValueError("Job already complete")
        return _round((a * b + a * first) / (a + b)), "days"
    if template_id == "PC_H_002_DelayedOutlet":
        a, b, c, first = (float(v[k]) for k in ("inlet_a_hours", "inlet_b_hours", "outlet_hours", "initial_hours"))
        denominator = c * (a + b) - a * b
        if first * (a + b) >= a * b or denominator <= 0:
            raise ValueError("Invalid tank phase transition")
        return _round(a * b * (c - first) / denominator), "hours"
    if template_id == "TSD_E_001_BasicDistance":
        return _round(float(v["speed"]) * float(v["time"])), "km"
    if template_id == "TSD_M_001_RelativeSpeedMeeting":
        return _round(float(v["distance_apart"]) / (float(v["speed1"]) + float(v["speed2"]))), "hours"
    if template_id == "TSD_H_001_TrainCrossPlatform":
        metres = float(v["train_length"]) + float(v["platform_length"])
        metres_per_second = float(v["speed"]) / 3.6
        return _round(metres / metres_per_second), "seconds"

    if template_id == "WT_E_001_WorkCompletedPercent":
        return _round(100 * float(v["days_worked"]) / float(v["total_time"])), "%"
    if template_id == "WT_M_001_CombinedWorkTwoPeople":
        a, b = float(v["person1_time"]), float(v["person2_time"])
        return _round((a * b) / (a + b)), "days"
    if template_id == "WT_H_001_JoinLeave":
        a, b, t = float(v["person1_time"]), float(v["person2_time"]), float(v["together_days"])
        done = t / a + t / b
        if done >= 1:
            raise ValueError("job already complete")
        return _round(t + (1 - done) * b), "days"

    if template_id == "PC_E_001_SingleInletPercent":
        return _round(100 * float(v["open_hours"]) / float(v["fill_time"])), "%"
    if template_id == "PC_M_001_TwoInlets":
        a, b = float(v["pipe1_fill_time"]), float(v["pipe2_fill_time"])
        return _round((a * b) / (a + b)), "hours"
    if template_id == "PC_H_001_TwoInletsOutlet":
        net = 1 / float(v["pipe1_fill_time"]) + 1 / float(v["pipe2_fill_time"]) - 1 / float(v["outlet_time"])
        if net <= 0:
            raise ValueError("non-positive net flow")
        return _round(1 / net), "hours"

    if template_id == "PLD_E_001_BasicProfitLossPercent":
        cp, sp = float(v["cost_price"]), float(v["selling_price"])
        return abs(_round((sp - cp) * 100 / cp)), "%"
    if template_id == "PLD_M_001_SuccessiveDiscount":
        mp = Decimal(str(v["marked_price"])); d1 = Decimal(str(v["discount1"])); d2 = Decimal(str(v["discount2"]))
        value = mp * (Decimal("100") - d1) / Decimal("100")
        value = value * (Decimal("100") - d2) / Decimal("100")
        return _round(value), "USD"
    if template_id == "PLD_H_001_MarkupSuccessiveDiscountProfit":
        cp = Decimal(str(v["cost_price"])); m = Decimal(str(v["markup"])); d1 = Decimal(str(v["discount1"])); d2 = Decimal(str(v["discount2"]))
        selling = cp * (Decimal("100") + m) / Decimal("100")
        selling = selling * (Decimal("100") - d1) / Decimal("100")
        selling = selling * (Decimal("100") - d2) / Decimal("100")
        return abs(_round((selling - cp) * Decimal("100") / cp)), "%"

    if template_id == "MR_E_001_ComponentQuantity":
        a, b, total = float(v["ratio1"]), float(v["ratio2"]), float(v["total_quantity"])
        return _round(total * a / (a + b)), "liters"
    if template_id == "MR_M_001_RatioAdjustment":
        a, b = float(v["initial_ratio_part1"]), float(v["initial_ratio_part2"])
        add, c, d = float(v["added_quantity"]), float(v["final_ratio_part1"]), float(v["final_ratio_part2"])
        denominator = c * b - d * a
        if denominator <= 0:
            raise ValueError("invalid ratio")
        return _round(d * add * (a + b) / denominator), "liters"
    if template_id == "MR_H_001_RepeatedReplacement":
        total, removed, n = float(v["vessel_capacity"]), float(v["replaced_quantity"]), int(v["repetitions"])
        if removed <= 0 or removed >= total:
            raise ValueError("invalid replacement")
        return _round(total * pow((total - removed) / total, n)), "liters"

    if template_id == "ABP_E_001_FutureAge":
        return _round(float(v["current_age"]) + float(v["years_future"])), "years"
    if template_id == "ABP_M_001_FutureRatio":
        a = int(v["person1_age"] + v["years_future"])
        b = int(v["person2_age"] + v["years_future"])
        divisor = math.gcd(a, b)
        return f"{a // divisor}:{b // divisor}", "ratio"
    if template_id == "ABP_H_001_DifferenceFutureMultiple":
        d, y, m = float(v["age_difference"]), float(v["years_future"]), float(v["future_multiple"])
        younger = d / (m - 1) - y
        if younger <= 0:
            raise ValueError("invalid age")
        return _round(younger), "years"

    raise ValueError(f"Unsupported verification template: {template_id}")
