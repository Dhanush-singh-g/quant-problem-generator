"""Reviewed mathematical models; AI never defines candidate-visible formulas."""
import copy
import json
import random
from pathlib import Path

from core.question_engine import build_question

RULES = json.loads((Path(__file__).resolve().parents[1] / "data/design_rules.json").read_text())


def number(minimum, maximum, unit, step=1):
    return {"type": "int", "min": minimum, "max": maximum, "step": step, "unit": unit}


PHASE_MODELS = [
    ("Time, Speed & Distance", {
        "template_id": "TSD_H_002_MeetAfterPause", "difficulty": "hard", "subdomain": "Multi-stage relative motion",
        "story_template": "Two vehicles A and B start {separation} km apart and move toward each other at {speed_a} km/h and {speed_b} km/h. After {initial_hours} hours, A stops for {pause_hours} hours while B continues. A then resumes at its original speed. They meet after A resumes. How many hours after the original start do they meet?",
        "variables": {"separation": number(600, 1200, "km", 50), "speed_a": number(40, 80, "km/h", 5), "speed_b": number(30, 60, "km/h", 5), "initial_hours": number(1, 2, "hours"), "pause_hours": number(1, 2, "hours")},
    }),
    ("Work & Time", {
        "template_id": "WT_H_002_WorkerJoins", "difficulty": "hard", "subdomain": "Sequential work phases",
        "story_template": "Worker A can finish a job alone in {a_days} days and worker B in {b_days} days. A works alone for {alone_days} days, then B joins. Both work at constant rates until completion. How many days does the entire job take from when A starts?",
        "variables": {"a_days": number(12, 30, "days"), "b_days": number(10, 25, "days"), "alone_days": number(2, 5, "days")},
    }),
    ("Pipes & Cisterns", {
        "template_id": "PC_H_002_DelayedOutlet", "difficulty": "hard", "subdomain": "Sequential tank phases",
        "story_template": "Two inlets can fill an empty tank individually in {inlet_a_hours} hours and {inlet_b_hours} hours. Both open together. After {initial_hours} hours, an outlet that empties a full tank in {outlet_hours} hours is also opened; both inlets remain open. All rates are constant. How many hours after the original start will the tank become full?",
        "variables": {"inlet_a_hours": number(8, 16, "hours"), "inlet_b_hours": number(8, 16, "hours"), "outlet_hours": number(16, 30, "hours"), "initial_hours": number(1, 2, "hours")},
    }),
]

MODELS = {
    template["template_id"]: (domain, copy.deepcopy(template))
    for domain, templates in RULES["templates"].items() for template in templates
}
MODELS.update({template["template_id"]: (domain, template) for domain, template in PHASE_MODELS})


def model_spec(model_id):
    if model_id not in MODELS:
        raise ValueError("Unreviewed mathematical model")
    return copy.deepcopy(MODELS[model_id])


def available_models(domain, difficulty):
    return [model_id for model_id, (dom, template) in MODELS.items()
            if dom == domain and template["difficulty"] == difficulty]


def generate_model_question(domain, difficulty, model_id=None):
    candidates = available_models(domain, difficulty)
    if not candidates or (model_id and model_id not in candidates):
        raise ValueError("No supported model for requested topic/difficulty")
    domain, template = model_spec(model_id or random.choice(candidates))
    question = build_question(domain, template)
    question["difficulty"] = template["difficulty"]
    question["generation_metadata"].update({
        "model_id": template["template_id"], "model_version": 1,
        "canonical_stem": question["story_text"], "truth_source": "reviewed_model",
        "parameter_units": {name: spec.get("unit", "text") for name, spec in template["variables"].items()},
    })
    return question
