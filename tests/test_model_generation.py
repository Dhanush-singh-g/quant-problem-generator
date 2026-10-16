import copy
import json
import random

import pytest

from core.model_registry import MODELS, generate_model_question, model_spec
from core.formula_engine import solve
from core.verification_engine import verify_solve
from services.model_validation import validate_model_question
from services.question_designer import redesign_batch
from core.cs_question_engine import FACTS, build_cs_question
from agents.difficulty_agent import classify_difficulty


@pytest.mark.parametrize("model_id", list(MODELS))
def test_registered_models_match_independent_solver(model_id):
    domain, spec = model_spec(model_id)
    random.seed(model_id)
    for _ in range(100):
        q = generate_model_question(domain, spec["difficulty"], model_id)
        assert validate_model_question(q)["validator"]["final_validation"] == "valid"
        assert q["difficulty"] == spec["difficulty"]


@pytest.mark.parametrize("field,value", [
    ("answer_unit", "bananas"), ("answer_value", 999999),
    ("canonical_solution", "Invented explanation"), ("story_text", "Invented story"),
])
def test_mutated_truth_cannot_be_published(field, value):
    q = generate_model_question("Time, Speed & Distance", "easy")
    q[field] = value
    with pytest.raises(ValueError):
        validate_model_question(q)


def test_duplicate_options_cannot_be_published():
    q = generate_model_question("Time, Speed & Distance", "easy")
    q["options"]["A"] = q["options"]["B"]
    with pytest.raises(ValueError):
        validate_model_question(q)


def test_even_small_answer_changes_cannot_be_published():
    q = generate_model_question("Time, Speed & Distance", "medium")
    q["answer_value"] += 0.01
    with pytest.raises(ValueError):
        validate_model_question(q)


@pytest.mark.parametrize("domain,band", sorted({(domain, row["difficulty"])
                                              for domain, rows in FACTS.items() for row in rows}))
def test_curated_cs_buckets_pass_publication(domain, band):
    for _ in range(20):
        q = build_cs_question(domain, band)
        q.update(classify_difficulty(q))
        assert validate_model_question(q)["mode"] == "deterministic_fact_bank"


def test_registry_returns_independent_specs():
    _, spec = model_spec("TSD_E_001_BasicDistance")
    spec["story_template"] = "corrupted"
    assert model_spec("TSD_E_001_BasicDistance")[1]["story_template"] != "corrupted"


def test_ai_output_cannot_change_truth(monkeypatch):
    q = generate_model_question("Time, Speed & Distance", "easy")
    original = copy.deepcopy(q)
    monkeypatch.setattr("services.question_designer.gateway.generate", lambda *a, **kw: (
        json.dumps({"questions": [{"id": q["id"], "context_id": "training",
                                   "story_text": "Speed doubles", "answer_value": 123}]}),
        {"source": "mock", "api_calls": 1},
    ))
    redesigned, meta = redesign_batch([q])
    assert validate_model_question(redesigned[0])
    for field in ("options", "answer_value", "answer_unit", "canonical_solution", "variables", "difficulty"):
        assert redesigned[0][field] == original[field]
    assert redesigned[0]["story_text"].endswith(original["story_text"])


def test_ai_failure_keeps_correct_question(monkeypatch):
    q = generate_model_question("Work & Time", "hard")
    original = copy.deepcopy(q)
    def unavailable(*args, **kwargs):
        raise TimeoutError("offline")
    monkeypatch.setattr("services.question_designer.gateway.generate", unavailable)
    redesigned, _ = redesign_batch([q])
    assert redesigned[0] == original
    assert validate_model_question(q)


@pytest.mark.parametrize("model_id,values,expected,unit", [
    ("TSD_H_002_MeetAfterPause", {"separation": 600, "speed_a": 60, "speed_b": 40, "initial_hours": 1, "pause_hours": 2}, 7.2, "hours"),
    ("WT_H_002_WorkerJoins", {"a_days": 12, "b_days": 12, "alone_days": 2}, 7, "days"),
    ("PC_H_002_DelayedOutlet", {"inlet_a_hours": 8, "inlet_b_hours": 8, "outlet_hours": 16, "initial_hours": 2}, 4.67, "hours"),
])
def test_phase_conservation_known_answers(model_id, values, expected, unit):
    assert solve(model_id, values)[:2] == (expected, unit)
    assert verify_solve(model_id, values) == (expected, unit)


def test_phase_models_reject_completion_before_transition():
    values = {"separation": 100, "speed_a": 60, "speed_b": 40, "initial_hours": 1, "pause_hours": 2}
    with pytest.raises(ValueError):
        solve("TSD_H_002_MeetAfterPause", values)
    with pytest.raises(ValueError):
        verify_solve("TSD_H_002_MeetAfterPause", values)
