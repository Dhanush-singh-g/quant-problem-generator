


"""AI-first quantitative designer: one Gemini call proposes one machine-verifiable question."""

from __future__ import annotations

import re
import uuid
import random

from services.ai_gateway import gateway
from services.semantic_math_verifier import verify_story_math_consistency
from utils.helpers import safe_parse_json
from core.ai_expression_engine import (
    evaluate_float,
    evaluate_decimal,
    operation_count,
    referenced_names,
)
from services.question_quality import (
    difficulty_features,
    structural_descriptor,
    diversity_check,
    plausible_distractors,
    validate_distractors,
    validate_variable_usage,
    validate_solution_rendering,
    validate_reference_frames,
    validate_constraints,
)


DIFFICULTY_OPS = {
    "easy": (1, 2),
    "medium": (3, 5),
    "hard": (5, 10),
}

DIFFICULTY_STEPS = {
    "easy": (1, 2),
    "medium": (3, 4),
    "hard": (4, 6),
}


def _prompt(
    domain: str,
    difficulty: str,
    avoid_signatures: list[str],
) -> str:
    lo, hi = DIFFICULTY_OPS[difficulty]
    step_lo, step_hi = DIFFICULTY_STEPS[difficulty]

    return f"""
You are the Design+Generator agent for QuantForge.

Your task is to create exactly ONE original, mathematically valid,
machine-verifiable quantitative aptitude MCQ specification.

Topic: {domain}
Requested difficulty: {difficulty}

DOMAIN SCOPE NOTE:
If the topic is Time, Speed & Distance, keep the question in quantitative aptitude
scope. Prefer distance-speed-time, relative speed, average speed, trains, boats,
races, circular tracks, meeting/overtaking, and delays. Do NOT drift into physics
kinematics such as acceleration equations unless acceleration is explicitly part of
the requested domain.

Recently used structures to avoid when practical:
{avoid_signatures[-12:]}

Your output will be checked by strict deterministic validators.
A mathematically inconsistent, semantically ambiguous, redundant, or
machine-unverifiable proposal will be rejected.

Return ONLY one valid JSON object.
Do not use markdown.
Do not include explanations outside the JSON.

Every response MUST contain these top-level keys:
subdomain, story_template, variables, answer_expression, answer_unit,
constraints, reasoning_steps, structure_name.

Never omit variables. Never return a story without an explicit numeric request.
If no independent constraint is useful, return "constraints": [].


========================
1. REQUIRED JSON SCHEMA
========================

{{
  "subdomain": "short descriptive label",

  "story_template":
    "Complete question using named placeholders such as {{speed}} for every changing numeric value.",

  "variables": {{
    "speed": {{
      "value": 45,
      "unit": "km/h",
      "role": "speed",
      "relative_to": "ground"
    }},
    "time": {{
      "value": 3,
      "unit": "hours",
      "role": "time",
      "relative_to": "none"
    }}
  }},

  "answer_expression": "speed * time",

  "answer_unit": "km",

  "constraints": [
    {{
      "left": "speed * time",
      "operator": "==",
      "right": "135"
    }}
  ],

  "reasoning_steps": [
    "Identify {{speed}} and {{time}} as the required quantities.",
    "Compute {{speed}} * {{time}}."
  ],

  "structure_name": "short_snake_case_name"
}}


========================
2. DESIGN THE MATH FIRST
========================

Before writing the story, internally determine:

1. what quantity the question asks for;
2. the minimum input variables required;
3. the exact answer_expression;
4. the mathematical relationships that must hold;
5. the appropriate units and reference frames;
6. only then write story_template around that mathematics.

Do not begin with a complicated story and then invent an expression afterward.

The story, variables, expression, constraints and reasoning_steps must all
describe the SAME mathematical model.


========================
3. VARIABLE RULES
========================

variables must contain 2-8 entries.

Every variable must contain exactly the required semantic information:

- value
- unit
- role
- relative_to

value:
- must be numeric;
- absolute value must be between 0.01 and 100000.

role should describe the mathematical meaning, for example:

- speed
- distance
- time
- percentage
- rate
- quantity
- age
- ratio
- cost
- work_rate

relative_to describes a reference frame when one exists, for example:

- ground
- train
- escalator
- walkway
- water
- person
- none

Use relative_to="none" when reference frames do not apply.


===================================
4. STRICT VARIABLE RELEVANCE RULE
===================================

EVERY variable supplied in variables MUST appear directly by name in
answer_expression.

This requirement is strict.

Before returning the JSON, internally verify:

set(variable keys)
==
set(variable names referenced by answer_expression)

A variable does NOT count as used merely because it appears in:

- story_template
- constraints
- reasoning_steps

If a variable does not directly participate in answer_expression:

REMOVE IT.

Also remove the corresponding unnecessary numeric fact from the story.

Do NOT create:

- decorative variables;
- contextual numeric facts;
- redundant quantities;
- unnecessary intermediate variables;
- variables used only to make the story appear harder.

Use the MINIMUM set of numeric variables necessary for the requested
calculation.

VARIABLE CLOSURE PROCEDURE

Before returning the final JSON, perform this exact internal check:

1. Read answer_expression.
2. Extract every variable name referenced by answer_expression.
3. Construct variables using ONLY those names.
4. Construct variable_metadata semantics using ONLY those same names.
5. Write story_template using ONLY those variables.
6. Verify again that the variable keys exactly match the variable names in answer_expression.

Never include an intermediate or decorative variable unless that exact variable
name appears in answer_expression. Do not create extra keys such as time_b,
remaining_distance, adjustment, multiplier, total_time or extra_time unless
those exact names are mathematically required and explicitly referenced by
answer_expression.

BAD:

variables:
  speed, distance, laps

answer_expression:
  distance / speed

INVALID because laps does not participate in the answer.

GOOD:

variables:
  speed, distance

answer_expression:
  distance / speed

Every supplied variable participates directly.


========================
5. EXPRESSION RULES
========================

answer_expression computes the final requested numeric answer.

It may contain ONLY:

- supplied variable names
- numeric constants
- parentheses
- +
- -
- *
- /
- **

Do NOT use:

- functions
- comparisons
- assignment
- unknown symbols
- external constants
- code
- attributes
- indexing

The expression should require approximately {lo}-{hi} arithmetic operations
for the requested difficulty.

Do not artificially increase operation count using useless arithmetic.

The final answer must be positive and meaningful for the story.


========================
6. STORY RULES
========================

story_template must:

- be unambiguous;
- provide all information required by answer_expression;
- ask for exactly ONE numeric answer;
- contain a placeholder for EVERY variable;
- contain no unnecessary numeric facts;
- be mathematically consistent with answer_expression;
- avoid trick wording.

Every changing numeric quantity must be represented by a named placeholder.

Do NOT place raw changing numeric values directly in the prose.
STORY CONCISENESS

Keep the candidate-facing question extremely short and mathematically focused.

- Prefer ONE sentence. Use TWO short sentences only when a real phase/change
  must be stated.
- Target roughly 15-45 words. Never exceed 60 words.
- State only the facts needed to solve the question, then ask the numeric
  question directly.
- Do not add names, scenery, explanations, backstory, or decorative context.
- Do not make a question longer to make it look harder.
- Difficulty must come from the mathematics, not from prose length.
- Every sentence must contribute directly to answer_expression.
- Do not explain the solution method inside story_template.

GOOD STYLE:
"Two trains {{distance}} apart move toward each other at {{speed_a}} and
{{speed_b}}. How long until they meet?"

For a genuine staged problem, keep the transition equally compact:
"Two trains are {{distance}} apart. A travels at {{speed_a}} but slows by
{{reduction}} for {{duration}} while B continues at {{speed_b}}; how long until
they meet?"

========================
7. PLACEHOLDERS AND UNITS
========================

QuantForge automatically renders each placeholder together with its unit.

Therefore NEVER write a unit immediately before or after a placeholder.

CORRECT:

"Train Alpha travels at {{speed_alpha}}."

"The track length is {{distance}}."

WRONG:

"Train Alpha travels at {{speed_alpha}} km/h."

"The track length is {{distance}} meters."

If speed_alpha has:

value = 90
unit = "km/h"

then {{speed_alpha}} automatically becomes:

90 km/h

Writing "km/h" again would produce:

90 km/h km/h


========================
8. REFERENCE FRAME RULES
========================

Reference frames must be physically and mathematically consistent.

Before returning the JSON, inspect every speed variable used together in
answer_expression.

If speeds are added or subtracted, verify that their meanings and
relative_to metadata make that operation valid.

For moving-walkway, escalator, boat-stream, train and relative-motion
problems, explicitly distinguish quantities such as:

- speed relative to ground;
- speed relative to the moving surface or medium;
- speed of the moving surface or medium relative to ground.

Example:

If a person walks at a speed measured relative to a moving walkway,
do NOT label that walking speed as ground-relative.

If a speed is already specified relative to ground, do NOT add or subtract
another object's speed merely to convert it to ground speed.

Never combine incompatible reference frames.


====================================
8A. MULTI-STAGE MOTION SAFETY RULES
====================================

For Time, Speed & Distance problems that contain more than one time phase
(for example: stops, starts later, slows down, speeds up, resumes, joins,
leaves, waits, or changes speed), build an internal phase ledger BEFORE
writing answer_expression.

For every phase, determine all of the following internally:

- the duration of that phase;
- which actors are moving during that phase;
- the speed/rate of EACH moving actor during that phase;
- whether the actors are closing distance, separating, or moving in the same
  direction;
- the total change in separation/work/quantity during that phase.

CRITICAL CONSERVATION RULES:

- If two actors move toward each other during a phase, BOTH actors contribute
  to the closing distance in that phase.
- If actor A stops but actor B continues moving, A contributes ZERO during the
  stopped interval and B still contributes normally.
- If actor A changes speed while actor B continues unchanged, use A's changed
  speed AND B's unchanged speed during that phase.
- Do not subtract the movement of only one actor when multiple actors are
  simultaneously changing the requested quantity.
- After each phase, compute the remaining separation/quantity from ALL
  contributions in that phase before moving to the next phase.

Before returning JSON, mentally recompute the result using this phase ledger
and verify that it exactly matches answer_expression.

Example principle (do not copy numbers):
If A and B move toward each other for t hours, and A temporarily uses speed_a2
while B keeps speed_b, then the first-phase closing distance is
(speed_a2 + speed_b) * t, NOT speed_a2 * t.

If A is stopped for t hours while B keeps moving toward A, the first-phase
closing distance is speed_b * t, NOT speed_a * t.


========================
9. CONSTRAINT RULES
========================

The constraints KEY is required, but the list may be empty when the story has
no independent relationship worth checking. Never invent a tautology merely to
fill this list. For multi-stage or tightly related facts, include meaningful,
machine-verifiable relationships asserted or implied by the story.

Each constraint must contain exactly:

- left
- operator
- right

Supported operators:

==
!=
<
<=
>
>=

left and right may contain ONLY:

- existing variable names
- numeric constants
- parentheses
- +
- -
- *
- /
- **

Do NOT introduce variables that are absent from variables.

Every constraint must evaluate to TRUE using the supplied values.

Constraints must verify meaningful relationships from the story.

Do NOT add trivial or tautological filler such as:

speed > 0
time > 0
distance == distance
speed * time == the already-computed final answer

solely to fill the list. If the only possible constraint would merely restate
answer_expression, return an empty constraints list instead.

Constraints cannot rescue an unused variable.
Every variable must still participate directly in answer_expression.

For multi-stage problems, encode the important mathematical relationships
asserted by the story.

This is especially important for:

- relative motion
- trains
- boats and streams
- moving walkways or escalators
- work and time
- pipes and cisterns
- mixtures
- ages
- percentages
- profit and loss

If two facts describe the same underlying quantity in different ways,
include a constraint that verifies their consistency.

answer_expression and constraints have different jobs:

answer_expression:
computes the requested final answer.

constraints:
verify that the numerical facts in the story are mutually consistent.


========================
10. REASONING RULES
========================

reasoning_steps must contain approximately {step_lo}-{step_hi} genuine
reasoning steps.

They must:

- explain the actual solution;
- follow the same mathematics as answer_expression;
- use the same named placeholders when referring to numeric values;
- contain no unstated assumptions;
- contain no irrelevant steps.

Example:

"Compute distance as {{speed}} * {{time}}."

Do not make reasoning longer merely to imitate difficulty.


========================
11. DIFFICULTY RULES
========================

Target difficulty: {difficulty}

Easy:
- direct relationships;
- few operations;
- minimal transformation.

Medium:
- multiple operations;
- one or more derived relationships;
- moderate reasoning.

Hard:
- multiple dependent relationships;
- genuine multi-stage reasoning;
- meaningful constraints;
- careful transformations or relative relationships.

Hard does NOT mean:

- larger numbers;
- longer prose;
- extra irrelevant variables;
- unnecessary arithmetic;
- artificial complexity.

The deterministic QuantForge classifier will determine the final stored
difficulty, so prioritize mathematical validity over forcing the requested
difficulty.
IMPORTANT DIFFICULTY PRINCIPLE:

Question difficulty must come from the mathematical reasoning required,
not from longer wording or unnecessary narrative complexity.

For Medium and Hard questions, increase mathematical depth through meaningful
relationships, intermediate calculations, multiple dependent stages, rate
relationships, percentage relationships, relative motion, or other genuine
reasoning steps.

Do not make a question Hard merely by adding more characters, events,
descriptive text, irrelevant values, or artificial complications.

A Hard question may still have a short 2-3 sentence story.

========================
12. ORIGINALITY
========================

Do not merely rename people or change numbers from a common template.

Prefer a genuinely different mathematical structure when possible.

Avoid recently used structure names when practical:

{avoid_signatures[-12:]}

structure_name should concisely describe the mathematical structure using
snake_case.


========================
13. FINAL INTERNAL CHECK
========================

Before returning the JSON, internally verify ALL of the following:

1. Output is valid JSON.
2. There are 2-8 variables.
3. Every variable appears in story_template.
4. Every variable appears directly in answer_expression.
5. answer_expression contains no unknown variables.
6. There are no unused numeric variables.
7. Units are not duplicated around placeholders.
8. Reference frames are compatible.
9. Every constraint uses only known variables.
10. Every constraint is numerically true.
11. Constraints are meaningful rather than filler.
12. reasoning_steps agree with answer_expression.
13. The story contains enough information to solve the problem.
14. The story asks for exactly one numeric answer.
15. The mathematical result is positive and meaningful.
16. The question contains no unnecessary numerical facts.
17. The structure is reasonably distinct from recently used structures.

If any check fails, FIX the proposal internally before returning it.

Return ONLY the final JSON object.
"""

def _human_unit(unit: str, value: float | int) -> str:
    """Use a natural singular unit for exactly-one values."""
    unit = str(unit or "").strip()
    if abs(float(value) - 1.0) > 1e-12:
        return unit

    singular = {
        "hours": "hour",
        "minutes": "minute",
        "seconds": "second",
        "days": "day",
        "meters": "meter",
        "metres": "metre",
        "kilometers": "kilometer",
        "kilometres": "kilometre",
        "miles": "mile",
    }
    return singular.get(unit.lower(), unit)


def _clean_rendered_story(story: str) -> str:
    """Repair harmless rendering artifacts without changing the math."""
    story = re.sub(r"\s+", " ", str(story)).strip()
    previous = None
    while previous != story:
        previous = story
        story = _DUPLICATED_UNIT_RE.sub(lambda m: m.group(1), story)
    story = re.sub(r"\s+([,.;:?])", r"\1", story)
    return story


def _render(
    template: str,
    variables: dict,
    variable_metadata: dict | None = None,
) -> str:
    names = set(
        re.findall(
            r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
            template,
        )
    )

    if not names or not names.issubset(variables):
        raise ValueError(
            "story placeholders do not match variables"
        )

    # Default behaviour remains available for callers that do not
    # provide semantic metadata.
    if variable_metadata is None:
        return template.format(**variables)

    rendered_values = {}

    for name, value in variables.items():
        metadata = variable_metadata.get(name, {})
        unit = str(metadata.get("unit", "")).strip()

        # Avoid unnecessary ".0" in user-facing question text.
        if isinstance(value, float) and value.is_integer():
            display_value = str(int(value))
        else:
            display_value = str(value)

        if unit and unit.lower() != "none":
            rendered_values[name] = f"{display_value} {_human_unit(unit, value)}"
        else:
            rendered_values[name] = display_value

    return template.format(**rendered_values)


def _format(value: float, unit: str) -> str:
    rounded = round(value, 2)

    if abs(rounded - round(rounded)) < 1e-9:
        rounded = int(round(rounded))

    if unit == "%":
        return f"{rounded}%"

    return f"{rounded} {_human_unit(unit, rounded)}".strip()


def _options(
    answer: float,
    unit: str,
    expression: str,
    variables: dict,
):
    distractors = plausible_distractors(
        expression,
        variables,
        answer,
        count=3,
    )

    check = validate_distractors(
        answer,
        distractors,
    )

    if not check["accepted"]:
        raise ValueError(
            f"distractor_failed:{check['reason']}"
        )

    values = [(True, answer), *[(False, value) for value in distractors]]
    random.SystemRandom().shuffle(values)

    letters = ["A", "B", "C", "D"]
    opts = {letter: _format(value, unit) for letter, (_, value) in zip(letters, values)}
    correct = next(letter for letter, (is_correct, _) in zip(letters, values) if is_correct)

    return opts, correct, distractors


_QUESTION_CUE_RE = re.compile(
    r"\b(what|how|calculate|determine|find|compute)\b",
    re.IGNORECASE,
)

_DUPLICATED_UNIT_RE = re.compile(
    r"\b(hours?|minutes?|seconds?|days?|kilomet(?:er|re)s?|meters?|metres?|kms?|km/h|m/s)"
    r"\s+\1\b",
    re.IGNORECASE,
)


def _validate_user_facing_story(story: str, difficulty: str) -> None:
    """Keep candidate prompts explicit, compact and free of rendering defects."""
    if not _QUESTION_CUE_RE.search(story):
        raise ValueError("story_missing_question_request")

    if _DUPLICATED_UNIT_RE.search(story):
        raise ValueError("duplicated_unit_in_story")

    words = re.findall(r"\b\w+[\w'/-]*\b", story)
    max_words = {"easy": 40, "medium": 50, "hard": 60}.get(difficulty, 50)
    if len(words) < 7:
        raise ValueError("story_too_short_to_be_clear")
    if len(words) > max_words:
        raise ValueError(f"story_too_long:{len(words)}>{max_words}")


def generate_ai_quant_question(
    domain: str,
    difficulty: str,
    recent_descriptors: list[dict] | None = None,
):
    difficulty = difficulty.lower()

    if difficulty not in DIFFICULTY_OPS:
        raise ValueError("invalid difficulty")

    raw, meta = gateway.generate(
        _prompt(
            domain,
            difficulty,
            [
                f"shape={x.get('shape', '')}; structure={x.get('structure_name', '')}; subdomain={x.get('subdomain', '')}"
                for x in (recent_descriptors or [])
            ],
        ),
        cache_ttl=0,
        retries=1,
        json_mode=True,
        temperature=0.45,
    )

    if not raw:
        return None, meta

    obj = safe_parse_json(raw)

    if not isinstance(obj, dict):
        return None, {
            **meta,
            "reason": "invalid_json",
        }

    required_fields = {
        "subdomain",
        "story_template",
        "variables",
        "answer_expression",
        "answer_unit",
        "reasoning_steps",
        "structure_name",
    }
    missing_fields = sorted(required_fields - set(obj))
    if missing_fields:
        return None, {
            **meta,
            "reason": "missing_required_fields:" + ",".join(missing_fields),
        }

    if obj.get("constraints") is None:
        obj["constraints"] = []

    try:
        # ---------------------------------------------------------
        # 1. PARSE STRUCTURED VARIABLES
        # ---------------------------------------------------------

        if not isinstance(obj.get("story_template"), str) or not obj["story_template"].strip():
            raise ValueError("bad_story_template")
        if not isinstance(obj.get("reasoning_steps"), list):
            raise ValueError("bad_reasoning_steps")
        if not isinstance(obj.get("constraints"), list):
            raise ValueError("bad_constraints")

        raw_variables = obj["variables"]

        if (
            not isinstance(raw_variables, dict)
            or not (2 <= len(raw_variables) <= 8)
        ):
            raise ValueError("bad variables")

        variables = {}
        variable_metadata = {}

        for raw_name, spec in raw_variables.items():
            name = str(raw_name)

            if not re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*",
                name,
            ):
                raise ValueError(
                    f"invalid variable name:{name}"
                )

            if not isinstance(spec, dict):
                raise ValueError(
                    f"variable {name} must contain semantic metadata"
                )

            if "value" not in spec:
                raise ValueError(
                    f"variable {name} missing value"
                )

            value = float(spec["value"])

            variables[name] = value

            variable_metadata[name] = {
                "unit": str(
                    spec.get("unit", "")
                ).strip()[:32],

                "role": str(
                    spec.get("role", "")
                ).strip().lower()[:32],

                "relative_to": str(
                    spec.get(
                        "relative_to",
                        "none",
                    )
                ).strip().lower()[:32],
            }

        if any(
            not (0.01 <= abs(v) <= 100000)
            for v in variables.values()
        ):
            raise ValueError("variable range")

        # ---------------------------------------------------------
        # 2. EXPRESSION VALIDATION
        # ---------------------------------------------------------

        expr = str(
            obj["answer_expression"]
        ).strip()

        expression_names = referenced_names(expr)

        if not expression_names.issubset(variables):
            raise ValueError(
                "expression variables"
            )

        ops = operation_count(expr)

        # The prompt targets a requested band, but the deterministic
        # classifier remains authoritative.
        max_ops = {
                "easy": 8,
                "medium": 16,
                "hard": 24,
            }.get(difficulty, 16)

        if not (1 <= ops <= max_ops):
                raise ValueError(
                    f"unsupported arithmetic complexity:{ops}"
                )

        # ---------------------------------------------------------
        # 3. STORY / VARIABLE SEMANTIC VALIDATION
        # ---------------------------------------------------------

        template = str(
            obj["story_template"]
        )

        constraints = obj.get(
            "constraints",
            [],
        )

        usage_check = validate_variable_usage(
            expr,
            variables,
            template,
            constraints,
        )

        if not usage_check["accepted"]:
            details = (
                usage_check.get("unused_variables")
                or usage_check.get("missing_variables")
                or usage_check.get("unknown_variables")
                or []
            )
            raise ValueError(
                "semantic_usage_failed:"
                f"{usage_check['reason']}:"
                f"{details}"
            )

        frame_check = validate_reference_frames(
            expr,
            variable_metadata,
        )

        if not frame_check["accepted"]:
            raise ValueError(
                "reference_frame_failed:"
                f"{frame_check['reason']}:"
                f"{frame_check.get('variables', [])}"
            )

        # ---------------------------------------------------------
        # 4. STORY CONSTRAINT CONSISTENCY
        # ---------------------------------------------------------

      

        constraint_check = validate_constraints(
            constraints,
            variables,
        )

        if not constraint_check["accepted"]:
            raise ValueError(
                "constraint_validation_failed:"
                f"{constraint_check['reason']}"
            )

        # ---------------------------------------------------------
        # 5. INDEPENDENT DETERMINISTIC SOLVERS
        # ---------------------------------------------------------

        a = evaluate_float(
            expr,
            variables,
        )

        b = float(
            evaluate_decimal(
                expr,
                variables,
            )
        )

        if abs(a - b) > max(
            1e-7,
            abs(a) * 1e-7,
        ):
            raise ValueError(
                "independent solver mismatch"
            )

        if a <= 0:
            raise ValueError(
                "non-positive answer"
            )

        # ---------------------------------------------------------
        # 5. PLACEHOLDER VALIDATION
        # ---------------------------------------------------------

        placeholders = set(
            re.findall(
                r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
                template,
            )
        )

        if placeholders != set(variables):
            raise ValueError(
                "every variable must appear exactly as "
                "a story placeholder"
            )

        if not expression_names.issubset(
            placeholders
        ):
            raise ValueError(
                "expression uses a variable not disclosed "
                "in the story"
            )

        # ---------------------------------------------------------
        # 6. RENDER FINAL STORY
        # ---------------------------------------------------------

        story = _clean_rendered_story(
            _render(
                template,
                variables,
                variable_metadata,
            )
        )

        _validate_user_facing_story(story, difficulty)

        unit = str(
            obj.get(
                "answer_unit",
                "",
            )
        ).strip()[:24]




                # ---------------------------------------------------------
        # 7. REASONING / SOLUTION RENDERING
        # ---------------------------------------------------------



        reasoning_steps = [
            str(x)
            for x in obj.get(
                "reasoning_steps",
                [],
            )
            if str(x).strip()
        ]

        solution_check = validate_solution_rendering(
            reasoning_steps,
            variables,
        )

        if not solution_check["accepted"]:
            raise ValueError(
                "solution_rendering_failed:"
                f"{solution_check['reason']}"
            )

        rendered_reasoning_steps = (
            solution_check["rendered_steps"]
        )

        # ---------------------------------------------------------
        # 8. DETERMINISTIC DIFFICULTY CLASSIFICATION
        # ---------------------------------------------------------

        diff = difficulty_features(
            expr,
            variables,
            reasoning_steps,
        )

        actual_difficulty = diff[
            "difficulty"
        ]

        # ---------------------------------------------------------
        # 9. STRUCTURAL DESCRIPTOR
        # ---------------------------------------------------------

        descriptor = structural_descriptor(
            domain,
            expr,
            variables,
            str(
                obj.get(
                    "structure_name",
                    "ai_structure",
                )
            ),
            str(
                obj.get(
                    "subdomain",
                    "general",
                )
            ),
        )

        # ---------------------------------------------------------
        # 10. DIVERSITY CHECK
        # ---------------------------------------------------------

        # If Gemini hits the requested difficulty, apply structural
        # diversity against recent questions in that bucket.
        #
        # If deterministic classification reassigns difficulty,
        # retain the valid work and rely on exact DB dedupe.
        diversity = diversity_check(
            descriptor,
            recent_descriptors or [],
        )

        if not diversity["accepted"]:
            raise ValueError(
                "diversity_rejected:"
                f"{diversity.get('reason', 'too_similar')}:"
                f"{diversity['max_similarity']}"
            )

        # ---------------------------------------------------------
        # 11. MCQ OPTIONS
        # ---------------------------------------------------------

        opts, correct, distractors = _options(
            a,
            unit,
            expr,
            variables,
        )

        # ---------------------------------------------------------
        # EXPENSIVE BLIND STORY <-> MATH VERIFICATION
        # Run this only after every cheap deterministic gate passes.
        # ---------------------------------------------------------
        semantic_math_check = verify_story_math_consistency(
            story_template=template,
            variables=variables,
            variable_metadata=variable_metadata,
            answer_expression=expr,
            answer_unit=unit,
            constraints=constraints,
        )

        meta = {
            **meta,
            "api_calls": int(meta.get("api_calls", 0) or 0)
            + int(semantic_math_check.get("api_calls", 0) or 0),
        }

        if not semantic_math_check["accepted"]:
            raise ValueError(
                "semantic_model_failed:"
                f"{semantic_math_check['reason']}:"
                f"{semantic_math_check.get('mismatch', '')}"
            )

        sig = descriptor[
            "fingerprint"
        ]

        # ---------------------------------------------------------
        # 12. FINAL QUESTION OBJECT
        # ---------------------------------------------------------

        return {
            "id": str(
                uuid.uuid4()
            ),

            "domain": domain,

            "difficulty": actual_difficulty,

            "story_text": story,

            "options": opts,

            "correct_option": correct,

            "canonical_solution": (
                " -> ".join(
                    rendered_reasoning_steps
                )[:2000]
            ),

            "answer_value": round(
                a,
                2,
            ),

            "answer_unit": unit,

            # Keep the existing flat numeric variable structure.
            # This preserves compatibility with the rest of the
            # application and expression engine.
            "variables": variables,

            "generation_metadata": {
                "question_family": "quantitative",

                "method": (
                    "ai_structured_verified"
                ),

                "ai_generated_structure": True,

                "answer_expression": expr,

                "structure_name": str(
                    obj.get(
                        "structure_name",
                        "ai_structure",
                    )
                )[:80],

                "structure_signature": sig,

                "subdomain": str(
                    obj.get(
                        "subdomain",
                        "general",
                    )
                )[:80],

                "requested_difficulty": (
                    difficulty
                ),

                "template_difficulty": (
                    actual_difficulty
                ),

                "difficulty_reassigned": (
                    actual_difficulty
                    != difficulty
                ),

                "operation_count": ops,

                "difficulty_score": diff[
                    "difficulty_score"
                ],

                "difficulty_features": diff,

                "structural_descriptor": (
                    descriptor
                ),

                "diversity": diversity,

                "distractor_strategy": (
                    "operator_mutation_then_"
                    "common_error_fallback"
                ),

                "distractor_values": [
                    round(x, 8)
                    for x in distractors
                ],

                # New semantic metadata.
                "variable_semantics": (
                    variable_metadata
                ),

                # Keep the exact machine-verifiable relationships
                # proposed for this question for later auditing.
                "story_constraints": constraints,

                "semantic_validation": {
                    "story_math_consistency": semantic_math_check,

                    "variable_usage": (
                        usage_check
                    ),

                    "reference_frames": (
                        frame_check
                    ),

                    "constraints": {
                        "accepted": constraint_check[
                            "accepted"
                        ],
                        "reason": constraint_check[
                            "reason"
                        ],
                        "constraint_count": (
                            constraint_check.get(
                                "constraint_count",
                                0,
                            )
                        ),
                    },

                    "solution_rendering": {
                        "accepted": (
                            solution_check[
                                "accepted"
                            ]
                        ),

                        "reason": (
                            solution_check[
                                "reason"
                            ]
                        ),
                    },
                },

                "quality_status": (
                    "validated"
                ),

                "independent_solver_a": round(
                    a,
                    8,
                ),

                "independent_solver_b": round(
                    b,
                    8,
                ),
            },
        }, meta

    except Exception as exc:
        return None, {
            **meta,
            "reason": (
                "proposal_rejected:"
                f"{str(exc)[:120]}"
            ),
        }