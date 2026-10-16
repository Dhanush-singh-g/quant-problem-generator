"""Offline validation for the deterministic quantitative pipeline.

Run from the project root:
    python scripts/validate_final_pass.py
No database, Redis or Gemini connection is required.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.question_engine import build_question
from agents.difficulty_agent import classify_difficulty
from agents.solver_agent_a import solve_a
from agents.solver_agent_b import solve_b
from agents.validator_agent import validate_answers

rules = json.loads((ROOT / "data" / "design_rules.json").read_text(encoding="utf-8"))
expected = {"easy", "medium", "hard"}

for domain, templates in rules["templates"].items():
    bands = {row.get("difficulty") for row in templates}
    if bands != expected:
        raise SystemExit(f"{domain}: expected {expected}, got {bands}")
    for template in templates:
        for _ in range(25):
            q = build_question(domain, template)
            q.update(classify_difficulty(q))
            result = validate_answers(q, solve_a(q), solve_b(q))
            if q["difficulty"] != template["difficulty"]:
                raise SystemExit(f"difficulty mismatch: {template['template_id']}")
            if result["final_validation"] != "valid":
                raise SystemExit(f"validation failed: {template['template_id']} -> {result}")

print("PASS: all 18 quantitative difficulty structures generated and independently validated.")
