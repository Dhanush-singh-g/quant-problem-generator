"""Independent, blind story-to-math verification for AI-generated questions.

The verifier deliberately does not see the generator's proposed expression in
its prompts. For multi-stage rate/motion stories, a second independent phase
ledger audit is required before the proposal may pass.
"""
from __future__ import annotations

import json
import re

from services.ai_gateway import gateway
from utils.helpers import safe_parse_json
from core.ai_expression_engine import evaluate_float, evaluate_decimal, referenced_names


_STAGE_WORDS_RE = re.compile(
    r"\b(stops?|stopped|pauses?|paused|waits?|waited|delay(?:ed)?|"
    r"slows?|slowed|reduces?|reduced|decreases?|decreased|increases?|increased|"
    r"speeds?\s+up|resumes?|resumed|joins?|joined|leaves?|left|temporar(?:y|ily)|"
    r"first\s+(?:half|segment|leg|phase|stage)|second\s+(?:half|segment|leg|phase|stage)|"
    r"third\s+(?:half|segment|leg|phase|stage)|additional\s+(?:time|distance|hour|minute|second)|"
    r"after\s+which|before\s+continuing|changes?\s+(?:its\s+)?speed)\b",
    re.IGNORECASE,
)


def _looks_multistage(story_template: str, variable_metadata: dict) -> bool:
    """Run the extra phase audit only for a genuine state or segment change.

    Plain phrases such as "meet after 3 hours" do not make a problem multi-stage.
    """
    rate_like = sum(
        1
        for meta in variable_metadata.values()
        if str(meta.get("role", "")).lower() in {"speed", "rate", "work_rate"}
    )
    if rate_like < 1:
        return False

    if _STAGE_WORDS_RE.search(story_template):
        return True

    time_like = sum(
        1
        for meta in variable_metadata.values()
        if str(meta.get("role", "")).lower() in {"time", "duration", "delay"}
    )
    return time_like >= 2


def _base_payload(
    story_template: str,
    variables: dict,
    variable_metadata: dict,
    answer_unit: str,
) -> dict:
    # IMPORTANT: generator constraints are intentionally excluded. They are
    # generator-authored and can anchor an independent verifier on the same bug.
    return {
        "story_template": story_template,
        "variables": {
            name: {"value": value, **variable_metadata.get(name, {})}
            for name, value in variables.items()
        },
        "expected_answer_unit": answer_unit,
    }


def _verification_prompt(
    story_template: str,
    variables: dict,
    variable_metadata: dict,
    answer_unit: str,
) -> str:
    payload = _base_payload(
        story_template,
        variables,
        variable_metadata,
        answer_unit,
    )
    return f"""
You are the independent mathematical verifier for QuantForge.

Derive the answer model ONLY from the story below. You are not being shown the
generator's proposed expression, constraints, or reasoning.

You must independently conserve the relevant quantity. For motion/rate stories:
- account for every actor that is active in every interval;
- if two actors move toward each other, both contribute to closing distance;
- if one actor stops, that actor contributes zero during the stopped interval;
- if one actor changes speed while another continues, include both actors with
  their correct speeds during that phase;
- update the remaining distance/work/quantity after each phase before starting
  the next one.

Use only supplied variable names, numeric constants, parentheses, +, -, *, /,
and **. Return an expression that directly computes the one numeric quantity
asked by the story. If the story is ambiguous or cannot be modeled reliably,
mark it ambiguous instead of guessing.

Question specification:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Return ONLY this JSON object:
{{
  "derived_expression": "machine evaluable expression using supplied variable names",
  "derived_unit": "unit of the requested answer",
  "ambiguous": false,
  "reason": "brief independent derivation summary"
}}
"""


def _phase_audit_prompt(
    story_template: str,
    variables: dict,
    variable_metadata: dict,
    answer_unit: str,
) -> str:
    payload = _base_payload(
        story_template,
        variables,
        variable_metadata,
        answer_unit,
    )
    return f"""
You are a SECOND independent mathematical auditor for QuantForge.

Do not guess the generator's formula. Build a chronological phase ledger from
the story and derive the answer from conservation of distance/work/quantity.

For EACH phase explicitly identify:
1. its duration or terminating event;
2. every actor/rate active in that phase;
3. each active actor's contribution;
4. the net change during the phase;
5. the remaining quantity after the phase.

Critical rules:
- If A and B both move toward each other, the phase closing rate contains BOTH.
- If A is stopped while B moves, A contributes zero and B still contributes.
- If A slows/speeds up while B continues, use A's changed rate AND B's rate.
- Never attribute distance to an actor that the story says is stationary.
- Never omit an actor that the story says continues moving.

Only after the ledger is internally consistent, derive one machine-evaluable
expression for the final requested answer.

Question specification:
{json.dumps(payload, ensure_ascii=False, indent=2)}

Return ONLY this JSON object:
{{
  "ambiguous": false,
  "phases": [
    {{
      "description": "short phase description",
      "active_actors": ["names or semantic labels"],
      "contribution_summary": "how the requested quantity changes in this phase"
    }}
  ],
  "derived_expression": "machine evaluable expression using supplied variable names",
  "derived_unit": "unit of the requested answer",
  "reason": "brief conservation-based audit"
}}
"""


def _evaluate_expression(expression: str, variables: dict) -> tuple[float, float]:
    unknown = referenced_names(expression) - set(variables)
    if unknown:
        raise ValueError(f"unknown variables: {sorted(unknown)}")

    as_float = evaluate_float(expression, variables)
    as_decimal = float(evaluate_decimal(expression, variables))
    tol = max(1e-7, abs(as_float) * 1e-7)
    if abs(as_float - as_decimal) > tol:
        raise ValueError("expression evaluator disagreement")
    return as_float, as_decimal


def _parse_derivation(raw: str | None, meta: dict, label: str) -> tuple[dict | None, dict | None]:
    api_calls = int(meta.get("api_calls", 0) or 0)
    if not raw:
        return None, {
            "accepted": False,
            "reason": f"{label}_unavailable",
            "mismatch": str(meta.get("reason", "no verifier response")),
            "api_calls": api_calls,
            "source": meta.get("source"),
        }

    obj = safe_parse_json(raw)
    if not isinstance(obj, dict) or "derived_expression" not in obj:
        return None, {
            "accepted": False,
            "reason": f"{label}_invalid_schema",
            "mismatch": "Verifier did not return a derived_expression.",
            "api_calls": api_calls,
            "source": meta.get("source"),
        }

    if obj.get("ambiguous") is True:
        return None, {
            "accepted": False,
            "reason": "semantic_story_ambiguous",
            "derived_relationship": str(obj.get("derived_expression", ""))[:1000],
            "mismatch": str(obj.get("reason", "story is ambiguous"))[:1000],
            "api_calls": api_calls,
            "source": meta.get("source"),
        }

    expression = str(obj.get("derived_expression", "")).strip()
    if not expression:
        return None, {
            "accepted": False,
            "reason": f"{label}_invalid_schema",
            "mismatch": "Verifier returned an empty derived_expression.",
            "api_calls": api_calls,
            "source": meta.get("source"),
        }

    return obj, None


def verify_story_math_consistency(
    story_template: str,
    variables: dict,
    variable_metadata: dict,
    answer_expression: str,
    answer_unit: str,
    constraints: list[dict],
) -> dict:
    # constraints remains in the public signature for compatibility, but is
    # intentionally NOT passed to either independent semantic verifier.
    del constraints

    raw, meta = gateway.generate(
        _verification_prompt(
            story_template=story_template,
            variables=variables,
            variable_metadata=variable_metadata,
            answer_unit=answer_unit,
        ),
        cache_ttl=0,
        retries=1,
        json_mode=True,
        temperature=0.0,
    )
    total_api_calls = int(meta.get("api_calls", 0) or 0)

    obj, error = _parse_derivation(raw, meta, "semantic_verifier")
    if error:
        return error

    derived_expression = str(obj["derived_expression"]).strip()

    try:
        proposed_float, _ = _evaluate_expression(answer_expression, variables)
        derived_float, _ = _evaluate_expression(derived_expression, variables)
    except Exception as exc:
        return {
            "accepted": False,
            "reason": "semantic_verifier_invalid_derivation",
            "derived_relationship": derived_expression[:1000],
            "mismatch": str(exc)[:1000],
            "api_calls": total_api_calls,
            "source": meta.get("source"),
        }

    tolerance = max(1e-6, abs(derived_float) * 1e-5, abs(proposed_float) * 1e-5)
    if abs(derived_float - proposed_float) > tolerance:
        return {
            "accepted": False,
            "reason": "semantic_model_mismatch",
            "derived_relationship": derived_expression[:1000],
            "derived_value": round(derived_float, 10),
            "proposed_value": round(proposed_float, 10),
            "mismatch": (
                f"Blind derivation evaluates to {derived_float}, while the proposed "
                f"model evaluates to {proposed_float}. Verifier note: "
                f"{str(obj.get('reason', ''))[:500]}"
            ),
            "api_calls": total_api_calls,
            "source": meta.get("source"),
        }

    phase_audit = None
    if _looks_multistage(story_template, variable_metadata):
        audit_raw, audit_meta = gateway.generate(
            _phase_audit_prompt(
                story_template=story_template,
                variables=variables,
                variable_metadata=variable_metadata,
                answer_unit=answer_unit,
            ),
            cache_ttl=0,
            retries=1,
            json_mode=True,
            temperature=0.0,
        )
        total_api_calls += int(audit_meta.get("api_calls", 0) or 0)

        audit_obj, audit_error = _parse_derivation(audit_raw, audit_meta, "phase_auditor")
        if audit_error:
            audit_error["api_calls"] = total_api_calls
            return audit_error

        audit_expression = str(audit_obj["derived_expression"]).strip()
        try:
            audit_float, _ = _evaluate_expression(audit_expression, variables)
        except Exception as exc:
            return {
                "accepted": False,
                "reason": "phase_auditor_invalid_derivation",
                "derived_relationship": audit_expression[:1000],
                "mismatch": str(exc)[:1000],
                "api_calls": total_api_calls,
                "source": audit_meta.get("source"),
            }

        audit_tolerance = max(
            1e-6,
            abs(audit_float) * 1e-5,
            abs(proposed_float) * 1e-5,
            abs(derived_float) * 1e-5,
        )

        if (
            abs(audit_float - proposed_float) > audit_tolerance
            or abs(audit_float - derived_float) > audit_tolerance
        ):
            return {
                "accepted": False,
                "reason": "phase_audit_mismatch",
                "derived_relationship": derived_expression[:1000],
                "phase_audit_relationship": audit_expression[:1000],
                "derived_value": round(derived_float, 10),
                "phase_audit_value": round(audit_float, 10),
                "proposed_value": round(proposed_float, 10),
                "mismatch": (
                    "Multi-stage phase audit disagrees with the proposed model or "
                    "the first blind derivation. "
                    f"Audit note: {str(audit_obj.get('reason', ''))[:500]}"
                ),
                "api_calls": total_api_calls,
                "source": audit_meta.get("source"),
            }

        phase_audit = {
            "accepted": True,
            "derived_relationship": audit_expression[:1000],
            "derived_value": round(audit_float, 10),
            "phases": audit_obj.get("phases", [])[:12]
            if isinstance(audit_obj.get("phases", []), list)
            else [],
            "reason": str(audit_obj.get("reason", ""))[:1000],
        }

    return {
        "accepted": True,
        "reason": "semantic_match_with_phase_audit" if phase_audit else "semantic_match",
        "derived_relationship": derived_expression[:1000],
        "derived_value": round(derived_float, 10),
        "proposed_value": round(proposed_float, 10),
        "mismatch": "",
        "phase_audit": phase_audit,
        "api_calls": total_api_calls,
        "source": meta.get("source"),
    }
