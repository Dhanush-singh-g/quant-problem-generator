import math
from decimal import Decimal, ROUND_HALF_UP


def _num(x):
    if isinstance(x, Decimal):
        if x == x.to_integral_value():
            return int(x)
        return float(x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    x = float(x)
    return int(round(x)) if abs(x - round(x)) < 1e-9 else round(x, 2)


def solve(template_id, v):
    if template_id in {"TSD_H_002_MeetAfterPause", "WT_H_002_WorkerJoins", "PC_H_002_DelayedOutlet"}:
        from core.phase_engine import solve_phases
        return solve_phases(template_id, v)
    # Time, Speed & Distance
    if template_id == "TSD_E_001_BasicDistance":
        ans = v["speed"] * v["time"]
        return _num(ans), "km", f"Distance = speed × time = {v['speed']} × {v['time']} = {_num(ans)} km"

    if template_id == "TSD_M_001_RelativeSpeedMeeting":
        relative = v["speed1"] + v["speed2"]
        if relative <= 0:
            raise ValueError("relative speed must be positive")
        ans = v["distance_apart"] / relative
        return _num(ans), "hours", (
            f"Opposite-direction relative speed = {v['speed1']} + {v['speed2']} = {relative} km/h; "
            f"time = {v['distance_apart']} / {relative} = {_num(ans)} hours"
        )

    if template_id == "TSD_H_001_TrainCrossPlatform":
        speed_mps = v["speed"] * 5 / 18
        total_length = v["train_length"] + v["platform_length"]
        if speed_mps <= 0:
            raise ValueError("speed must be positive")
        ans = total_length / speed_mps
        return _num(ans), "seconds", (
            f"Distance to clear platform = {v['train_length']} + {v['platform_length']} = {total_length} m. "
            f"Speed = {v['speed']} × 5/18 = {_num(speed_mps)} m/s. "
            f"Time = {total_length} / {_num(speed_mps)} = {_num(ans)} seconds"
        )

    # Work & Time
    if template_id == "WT_E_001_WorkCompletedPercent":
        if v["days_worked"] >= v["total_time"]:
            raise ValueError("easy work question requires a partial job")
        ans = v["days_worked"] / v["total_time"] * 100
        return _num(ans), "%", (
            f"Work completed = {v['days_worked']}/{v['total_time']} of the job = {_num(ans)}%"
        )

    if template_id == "WT_M_001_CombinedWorkTwoPeople":
        a, b = v["person1_time"], v["person2_time"]
        rate = 1 / a + 1 / b
        ans = 1 / rate
        return _num(ans), "days", f"Combined rate = 1/{a} + 1/{b}; time = 1/rate = {_num(ans)} days"

    if template_id == "WT_H_001_JoinLeave":
        a, b, together = v["person1_time"], v["person2_time"], v["together_days"]
        combined_rate = 1 / a + 1 / b
        completed = together * combined_rate
        if completed >= 1:
            raise ValueError("job would already be complete before worker A leaves")
        remaining = 1 - completed
        b_days = remaining * b
        ans = together + b_days
        return _num(ans), "days", (
            f"Together they complete {together} × (1/{a} + 1/{b}) = {_num(completed)} of the job. "
            f"Remaining work = {_num(remaining)}. B needs {_num(b_days)} more days, "
            f"so total time = {_num(ans)} days"
        )

    # Pipes & Cisterns
    if template_id == "PC_E_001_SingleInletPercent":
        if v["open_hours"] >= v["fill_time"]:
            raise ValueError("easy pipe question requires a partially filled tank")
        ans = v["open_hours"] / v["fill_time"] * 100
        return _num(ans), "%", (
            f"Filled fraction = {v['open_hours']}/{v['fill_time']}; percentage = {_num(ans)}%"
        )

    if template_id == "PC_M_001_TwoInlets":
        a, b = v["pipe1_fill_time"], v["pipe2_fill_time"]
        net = 1 / a + 1 / b
        ans = 1 / net
        return _num(ans), "hours", f"Combined fill rate = 1/{a} + 1/{b}; time = {_num(ans)} hours"

    if template_id == "PC_H_001_TwoInletsOutlet":
        a, b, c = v["pipe1_fill_time"], v["pipe2_fill_time"], v["outlet_time"]
        net = 1 / a + 1 / b - 1 / c
        if net <= 0:
            raise ValueError("outlet cancels or exceeds inlet flow")
        ans = 1 / net
        return _num(ans), "hours", (
            f"Net rate = 1/{a} + 1/{b} − 1/{c} = {_num(net)} tank/hour; "
            f"time = 1/net rate = {_num(ans)} hours"
        )

    # Profit, Loss & Discount
    if template_id == "PLD_E_001_BasicProfitLossPercent":
        cp, sp = v["cost_price"], v["selling_price"]
        pct = (sp - cp) / cp * 100
        kind = "profit" if pct >= 0 else "loss"
        ans = abs(_num(pct))
        return ans, "%", f"{kind.title()} % = |({sp} − {cp})/{cp}| × 100 = {ans}%"

    if template_id == "PLD_M_001_SuccessiveDiscount":
        mp = Decimal(str(v["marked_price"])); d1 = Decimal(str(v["discount1"])); d2 = Decimal(str(v["discount2"]))
        after_first = mp * (Decimal("1") - d1 / Decimal("100"))
        ans = after_first * (Decimal("1") - d2 / Decimal("100"))
        return _num(ans), "USD", (
            f"After first discount: {v['marked_price']} × (1 − {v['discount1']}/100) = {_num(after_first)}. "
            f"After second discount: {_num(after_first)} × (1 − {v['discount2']}/100) = {_num(ans)} USD"
        )

    if template_id == "PLD_H_001_MarkupSuccessiveDiscountProfit":
        cp = Decimal(str(v["cost_price"])); markup = Decimal(str(v["markup"])); d1 = Decimal(str(v["discount1"])); d2 = Decimal(str(v["discount2"]))
        mp = cp * (Decimal("1") + markup / Decimal("100"))
        sp = mp * (Decimal("1") - d1 / Decimal("100")) * (Decimal("1") - d2 / Decimal("100"))
        pct = (sp - cp) / cp * Decimal("100")
        kind = "profit" if pct >= 0 else "loss"
        ans = abs(_num(pct))
        return ans, "%", (
            f"Marked price = {v['cost_price']} × (1 + {v['markup']}/100) = {_num(mp)}. "
            f"After both discounts SP = {_num(sp)}. {kind.title()} % = |({_num(sp)} − {v['cost_price']})/{v['cost_price']}| × 100 = {ans}%"
        )

    # Mixtures & Ratio
    if template_id == "MR_E_001_ComponentQuantity":
        a, b, total = v["ratio1"], v["ratio2"], v["total_quantity"]
        if a <= 0 or b <= 0:
            raise ValueError("ratio parts must be positive")
        ans = total * a / (a + b)
        return _num(ans), "liters", (
            f"Requested component = {a}/({a}+{b}) × {total} = {_num(ans)} liters"
        )

    if template_id == "MR_M_001_RatioAdjustment":
        a, b = v["initial_ratio_part1"], v["initial_ratio_part2"]
        q, c, d = v["added_quantity"], v["final_ratio_part1"], v["final_ratio_part2"]
        den = c * b - d * a
        if den <= 0:
            raise ValueError("inconsistent mixture ratios")
        total = d * q * (a + b) / den
        if total <= 0:
            raise ValueError("non-positive mixture quantity")
        return _num(total), "liters", (
            f"Let initial quantities be ax and bx. (ax + {q})/(bx) = {c}/{d}. "
            f"Solving gives initial total = {_num(total)} liters"
        )

    if template_id == "MR_H_001_RepeatedReplacement":
        total, removed, n = v["vessel_capacity"], v["replaced_quantity"], v["repetitions"]
        if removed <= 0 or removed >= total:
            raise ValueError("replacement quantity must be between zero and vessel capacity")
        retained_fraction = (1 - removed / total) ** n
        ans = total * retained_fraction
        return _num(ans), "liters", (
            f"Original liquid remaining = {total} × (1 − {removed}/{total})^{n} = {_num(ans)} liters"
        )

    # Age-Based Problems
    if template_id == "ABP_E_001_FutureAge":
        ans = v["current_age"] + v["years_future"]
        return _num(ans), "years", f"Future age = {v['current_age']} + {v['years_future']} = {_num(ans)} years"

    if template_id == "ABP_M_001_FutureRatio":
        a = v["person1_age"] + v["years_future"]
        b = v["person2_age"] + v["years_future"]
        g = math.gcd(int(a), int(b))
        ratio = f"{int(a)//g}:{int(b)//g}"
        return ratio, "ratio", f"Future ages = {a} and {b}; simplified ratio = {ratio}"

    if template_id == "ABP_H_001_DifferenceFutureMultiple":
        diff, years, multiple = v["age_difference"], v["years_future"], v["future_multiple"]
        den = multiple - 1
        younger = (diff - den * years) / den
        if younger <= 0:
            raise ValueError("generated age relationship has no positive current age")
        older = younger + diff
        if abs((older + years) - multiple * (younger + years)) > 1e-6:
            raise ValueError("generated age relationship is inconsistent")
        return _num(younger), "years", (
            f"Let the younger age be y. Then older age is y + {diff}. "
            f"y + {diff} + {years} = {multiple}(y + {years}); solving gives y = {_num(younger)} years"
        )

    raise ValueError(f"Unsupported template: {template_id}")


def equivalent(a, b, tol=1e-6):
    try:
        fa, fb = float(a), float(b)
        # Displayed quantitative answers are rounded to at most two decimals.
        # Independent algebraic implementations can land on opposite sides of a
        # binary-floating rounding boundary, so compare at displayed precision.
        if fa.is_integer() and fb.is_integer():
            return abs(fa - fb) <= tol
        return abs(fa - fb) <= max(0.011, tol * max(1, abs(fa), abs(fb)))
    except (TypeError, ValueError):
        return str(a).strip().lower() == str(b).strip().lower()
