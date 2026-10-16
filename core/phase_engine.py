"""Supported multi-stage models, expressed as conserved quantities per phase."""
from dataclasses import dataclass
from core.formula_engine import _num


@dataclass(frozen=True)
class Phase:
    description: str
    duration: float
    rate: float
    remaining: float


def solve_phases(model_id, v):
    phases = []
    if model_id == "TSD_H_002_MeetAfterPause":
        a, b, total = v["speed_a"], v["speed_b"], v["separation"]
        first, pause = v["initial_hours"], v["pause_hours"]
        remaining = total - (a + b) * first
        phases.append(Phase("Both vehicles approach", first, a + b, remaining))
        remaining -= b * pause
        phases.append(Phase("A is stopped; B continues", pause, b, remaining))
        if remaining <= 0:
            raise ValueError("Vehicles must meet after A resumes")
        final = remaining / (a + b)
        phases.append(Phase("Both vehicles approach again", final, a + b, 0))
        answer, unit = _num(first + pause + final), "hours"
        rate_unit, quantity_unit = "km/h", "km"
    elif model_id == "WT_H_002_WorkerJoins":
        a, b, first = v["a_days"], v["b_days"], v["alone_days"]
        remaining = 1 - first / a
        if remaining <= 0:
            raise ValueError("Work must remain when B joins")
        phases.append(Phase("A works alone", first, 1 / a, remaining))
        final = remaining / (1 / a + 1 / b)
        phases.append(Phase("A and B work together", final, 1 / a + 1 / b, 0))
        answer, unit = _num(first + final), "days"
        rate_unit, quantity_unit = "jobs/day", "jobs"
    elif model_id == "PC_H_002_DelayedOutlet":
        a, b, c, first = v["inlet_a_hours"], v["inlet_b_hours"], v["outlet_hours"], v["initial_hours"]
        inlet_rate = 1 / a + 1 / b
        remaining = 1 - first * inlet_rate
        net_rate = inlet_rate - 1 / c
        if remaining <= 0 or net_rate <= 0:
            raise ValueError("Tank must remain unfilled and net inflow must be positive")
        phases.append(Phase("Both inlets open", first, inlet_rate, remaining))
        final = remaining / net_rate
        phases.append(Phase("Both inlets and outlet open", final, net_rate, 0))
        answer, unit = _num(first + final), "hours"
        rate_unit, quantity_unit = "tanks/hour", "tanks"
    else:
        raise ValueError(f"Unsupported phase model: {model_id}")
    explanation = "; ".join(
        f"{p.description}: duration={p.duration:.6g} {unit}, "
        f"net rate={p.rate:.6g} {rate_unit}, remaining={p.remaining:.6g} {quantity_unit}"
        for p in phases
    )
    return answer, unit, f"{explanation}. Total elapsed time = {answer} {unit}."
