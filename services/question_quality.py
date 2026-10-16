

"""Deterministic quality gates for AI-proposed quantitative questions.

The LLM may propose a structure, but this module decides whether that proposal is
sufficiently different, appropriately difficult, and has plausible MCQ distractors.
No LLM call is made here.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import math
import re

from core.ai_expression_engine import (
    evaluate_float,
    evaluate_decimal,
    operation_count,
    structure_signature,
    referenced_names,
)


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall((value or "").lower()))


# ---------------------------------------------------------------------------
# SEMANTIC QUALITY GATES
# ---------------------------------------------------------------------------
def validate_variable_usage(
    expression: str,
    variables: dict,
    story_template: str,
    constraints: list[dict] | None = None,
) -> dict:
    """
    Reject irrelevant numeric variables.

    Every supplied variable must:
    1. appear in the story, and
    2. participate directly in the requested answer expression.

    Constraints validate consistency between story facts, but they are not
    allowed to make an otherwise irrelevant variable relevant.
    """

    expression_names = referenced_names(
        expression
    )

    variable_names = set(
        variables
    )

    unknown_expression_variables = (
        expression_names
        - variable_names
    )

    if unknown_expression_variables:
        return {
            "accepted": False,
            "reason": "expression_unknown_variables",
            "unknown_variables": sorted(
                unknown_expression_variables
            ),
        }

    unused = (
        variable_names
        - expression_names
    )

    if unused:
        return {
            "accepted": False,
            "reason": "unused_variables",
            "unused_variables": sorted(
                unused
            ),
        }

    placeholders = set(
        re.findall(
            r"\{([A-Za-z_][A-Za-z0-9_]*)\}",
            story_template,
        )
    )

    missing_from_story = (
        variable_names
        - placeholders
    )

    if missing_from_story:
        return {
            "accepted": False,
            "reason": "variables_missing_from_story",
            "missing_variables": sorted(
                missing_from_story
            ),
        }

    unknown_story_variables = (
        placeholders
        - variable_names
    )

    if unknown_story_variables:
        return {
            "accepted": False,
            "reason": "story_contains_unknown_variables",
            "unknown_variables": sorted(
                unknown_story_variables
            ),
        }

    return {
        "accepted": True,
        "reason": "all_variables_required",
        "unused_variables": [],
        "expression_variables": sorted(
            expression_names
        ),
    }   

def validate_solution_rendering(
    reasoning_steps: list[str],
    variables: dict,
) -> dict:
    """
    Render named variable placeholders inside Gemini's reasoning steps.

    Example:
        "Distance = {speed} * {time}"

    becomes:
        "Distance = 45.0 * 3.0"

    Any unknown or unresolved placeholder causes rejection.
    """

    if not reasoning_steps:
        return {
            "accepted": False,
            "reason": "missing_reasoning_steps",
            "rendered_steps": [],
        }

    rendered_steps = []

    for step in reasoning_steps:
        step = str(step).strip()

        if not step:
            continue

        try:
            rendered = step.format(**variables)

        except KeyError as exc:
            return {
                "accepted": False,
                "reason": f"unknown_solution_placeholder:{exc}",
                "rendered_steps": [],
            }

        except (ValueError, IndexError) as exc:
            return {
                "accepted": False,
                "reason": f"invalid_solution_placeholder:{exc}",
                "rendered_steps": [],
            }

        # After formatting, no named placeholder should remain.
        if re.search(
            r"\{[A-Za-z_][A-Za-z0-9_]*\}",
            rendered,
        ):
            return {
                "accepted": False,
                "reason": "unresolved_solution_placeholder",
                "rendered_steps": [],
            }

        rendered_steps.append(rendered)

    if not rendered_steps:
        return {
            "accepted": False,
            "reason": "missing_reasoning_steps",
            "rendered_steps": [],
        }

    return {
        "accepted": True,
        "reason": "solution_rendered",
        "rendered_steps": rendered_steps,
    }


def validate_reference_frames(
    expression: str,
    variable_metadata: dict,
) -> dict:
    """
    Detect an important class of relative-speed semantic errors.

    Example of an invalid expression:

        bob_ground_speed + escalator_speed

    when bob_ground_speed has already been explicitly defined relative to
    the ground.

    The check is intentionally conservative. It only examines addition and
    subtraction involving variables whose semantic role is "speed".
    """

    tree = ast.parse(expression, mode="eval")

    def names_under(node) -> set[str]:
        return {
            child.id
            for child in ast.walk(node)
            if isinstance(child, ast.Name)
        }

    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp):
            continue

        if not isinstance(
            node.op,
            (ast.Add, ast.Sub),
        ):
            continue

        left_names = names_under(node.left)
        right_names = names_under(node.right)

        for left in left_names:
            for right in right_names:
                left_meta = variable_metadata.get(
                    left,
                    {},
                )

                right_meta = variable_metadata.get(
                    right,
                    {},
                )

                if left_meta.get("role") != "speed":
                    continue

                if right_meta.get("role") != "speed":
                    continue

                left_frame = left_meta.get(
                    "relative_to",
                    "none",
                )

                right_frame = right_meta.get(
                    "relative_to",
                    "none",
                )

                # If one speed is already relative to the ground while
                # another is relative to a moving object/platform, combining
                # them directly is suspicious and is rejected.
                #
                # This catches cases such as:
                #
                # bob_run_speed relative_to ground
                # escalator_speed relative_to escalator
                #
                # bob_run_speed + escalator_speed
                #
                # which would double-count the platform movement.

                incompatible = (
                    left_frame == "ground"
                    and right_frame
                    not in {"ground", "none"}
                ) or (
                    right_frame == "ground"
                    and left_frame
                    not in {"ground", "none"}
                )

                if incompatible:
                    return {
                        "accepted": False,
                        "reason": (
                            "incompatible_speed_reference_frames"
                        ),
                        "variables": [
                            left,
                            right,
                        ],
                        "frames": [
                            left_frame,
                            right_frame,
                        ],
                    }

    return {
        "accepted": True,
        "reason": "reference_frames_consistent",
    }

def validate_constraints(
    constraints: list[dict],
    variables: dict,
    relative_tolerance: float = 1e-4,
    absolute_tolerance: float = 1e-6,
) -> dict:
    """
    Validate machine-readable mathematical constraints asserted by the story.

    Each constraint must have the form:

        {
            "left": "speed * time",
            "operator": "==",
            "right": "distance"
        }

    Both sides are evaluated independently using the restricted arithmetic
    DSL. Float and Decimal evaluators must agree before the constraint itself
    is checked.

    Supported comparison operators:

        ==
        !=
        <
        <=
        >
        >=
    """

    # Constraints are useful only when the story contains an independent
    # relationship worth checking. Forcing one for every simple question causes
    # the generator to invent tautologies and creates avoidable rejections.
    if constraints is None or constraints == []:
        return {
            "accepted": True,
            "reason": "no_independent_constraints",
            "constraint_count": 0,
            "checked_constraints": [],
        }

    if not isinstance(constraints, list):
        return {
            "accepted": False,
            "reason": "invalid_constraints_format",
            "checked_constraints": [],
        }

    supported_operators = {
        "==",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
    }

    checked = []

    for index, constraint in enumerate(constraints):
        if not isinstance(constraint, dict):
            return {
                "accepted": False,
                "reason": "invalid_constraint",
                "constraint_index": index,
                "checked_constraints": checked,
            }

        left = str(
            constraint.get("left", "")
        ).strip()

        right = str(
            constraint.get("right", "")
        ).strip()

        operator = str(
            constraint.get("operator", "")
        ).strip()

        if not left or not right:
            return {
                "accepted": False,
                "reason": "empty_constraint_expression",
                "constraint_index": index,
                "checked_constraints": checked,
            }

        if operator not in supported_operators:
            return {
                "accepted": False,
                "reason": "unsupported_constraint_operator",
                "constraint_index": index,
                "operator": operator,
                "checked_constraints": checked,
            }

        try:
            left_names = referenced_names(left)
            right_names = referenced_names(right)
        except Exception as exc:
            return {
                "accepted": False,
                "reason": "invalid_constraint_expression",
                "constraint_index": index,
                "error": str(exc),
                "checked_constraints": checked,
            }

        referenced = left_names | right_names

        unknown = referenced - set(variables)

        if unknown:
            return {
                "accepted": False,
                "reason": "constraint_unknown_variables",
                "constraint_index": index,
                "unknown_variables": sorted(unknown),
                "checked_constraints": checked,
            }

        try:
            left_float = evaluate_float(
                left,
                variables,
            )

            right_float = evaluate_float(
                right,
                variables,
            )

            left_decimal = float(
                evaluate_decimal(
                    left,
                    variables,
                )
            )

            right_decimal = float(
                evaluate_decimal(
                    right,
                    variables,
                )
            )

        except Exception as exc:
            return {
                "accepted": False,
                "reason": "constraint_evaluation_failed",
                "constraint_index": index,
                "error": str(exc),
                "checked_constraints": checked,
            }

        left_solver_tolerance = max(
            absolute_tolerance,
            abs(left_float) * relative_tolerance,
        )

        right_solver_tolerance = max(
            absolute_tolerance,
            abs(right_float) * relative_tolerance,
        )

        if abs(
            left_float - left_decimal
        ) > left_solver_tolerance:
            return {
                "accepted": False,
                "reason": "constraint_solver_disagreement",
                "constraint_index": index,
                "side": "left",
                "checked_constraints": checked,
            }

        if abs(
            right_float - right_decimal
        ) > right_solver_tolerance:
            return {
                "accepted": False,
                "reason": "constraint_solver_disagreement",
                "constraint_index": index,
                "side": "right",
                "checked_constraints": checked,
            }

        comparison_tolerance = max(
            absolute_tolerance,
            abs(left_float) * relative_tolerance,
            abs(right_float) * relative_tolerance,
        )

        approximately_equal = (
            abs(left_float - right_float)
            <= comparison_tolerance
        )

        if operator == "==":
            satisfied = approximately_equal

        elif operator == "!=":
            satisfied = not approximately_equal

        elif operator == "<":
            satisfied = (
                left_float
                < right_float - comparison_tolerance
            )

        elif operator == "<=":
            satisfied = (
                left_float
                <= right_float + comparison_tolerance
            )

        elif operator == ">":
            satisfied = (
                left_float
                > right_float + comparison_tolerance
            )

        else:
            satisfied = (
                left_float
                >= right_float - comparison_tolerance
            )

        result = {
            "index": index,
            "left": left,
            "operator": operator,
            "right": right,
            "left_value": left_float,
            "right_value": right_float,
            "satisfied": satisfied,
        }

        checked.append(result)

        if not satisfied:
            return {
                "accepted": False,
                "reason": "constraint_not_satisfied",
                "constraint_index": index,
                "failed_constraint": result,
                "checked_constraints": checked,
            }

    return {
        "accepted": True,
        "reason": "all_constraints_satisfied",
        "constraint_count": len(checked),
        "checked_constraints": checked,
    }
# ---------------------------------------------------------------------------
# EXISTING DIFFICULTY LOGIC
# ---------------------------------------------------------------------------

def expression_depth(expression: str) -> int:
    tree = ast.parse(expression, mode="eval")

    def depth(node) -> int:
        if isinstance(node, ast.Expression):
            return depth(node.body)

        if isinstance(node, ast.BinOp):
            return 1 + max(
                depth(node.left),
                depth(node.right),
            )

        if isinstance(node, ast.UnaryOp):
            return 1 + depth(node.operand)

        return 0

    return depth(tree)


def difficulty_features(
    expression: str,
    variables: dict,
    reasoning_steps: list[str] | None = None,
) -> dict:

    steps = [
        str(x).strip()
        for x in (reasoning_steps or [])
        if str(x).strip()
    ]

    ops = operation_count(expression)

    var_count = len(variables)

    depth = expression_depth(expression)

    tree = ast.parse(
        expression,
        mode="eval",
    )

    divisions = sum(
        isinstance(n, ast.BinOp)
        and isinstance(n.op, ast.Div)
        for n in ast.walk(tree)
    )

    powers = sum(
        isinstance(n, ast.BinOp)
        and isinstance(n.op, ast.Pow)
        for n in ast.walk(tree)
    )

    # This is intentionally transparent and deterministic.
    # Arithmetic workload is dominant; variable count,
    # nesting and multi-step reasoning add smaller costs.

    score = (
        ops * 2
        + max(0, var_count - 2)
        + min(2, max(0, len(steps) - 1))
        + max(0, depth - 2)
        + divisions
        + powers * 2
    )

    if score <= 7:
        band = "easy"

    elif score <= 14:
        band = "medium"

    else:
        band = "hard"

    return {
        "difficulty": band,
        "difficulty_score": score,
        "operation_count": ops,
        "variable_count": var_count,
        "reasoning_step_count": len(steps),
        "expression_depth": depth,
        "division_count": divisions,
        "power_count": powers,
    }


# ---------------------------------------------------------------------------
# EXISTING STRUCTURAL DIVERSITY LOGIC
# ---------------------------------------------------------------------------

def structural_descriptor(
    domain: str,
    expression: str,
    variables: dict,
    structure_name: str,
    subdomain: str,
) -> dict:

    shape = structure_signature(
        expression
    )

    descriptor = {
        "domain": domain,

        "shape": shape,

        "variable_count": len(
            variables
        ),

        "structure_name": re.sub(
            r"[^a-z0-9_]+",
            "_",
            (structure_name or "").lower(),
        ).strip("_")[:80],

        "subdomain": re.sub(
            r"\s+",
            " ",
            (subdomain or "").lower(),
        ).strip()[:80],
    }

    raw = "|".join(
        str(descriptor[k])
        for k in (
            "domain",
            "shape",
            "variable_count",
            "structure_name",
            "subdomain",
        )
    )

    descriptor["fingerprint"] = (
        hashlib.sha256(
            raw.encode("utf-8")
        )
        .hexdigest()[:32]
    )

    return descriptor


def structural_similarity(
    candidate: dict,
    existing: dict,
) -> float:
    """0..1 score. Exact mathematical shape is heavily weighted."""

    shape_score = (
        1.0
        if candidate.get("shape")
        == existing.get("shape")
        else 0.0
    )

    c_tokens = _tokens(
        f"{candidate.get('structure_name', '')} "
        f"{candidate.get('subdomain', '')}"
    )

    e_tokens = _tokens(
        f"{existing.get('structure_name', '')} "
        f"{existing.get('subdomain', '')}"
    )

    union = c_tokens | e_tokens

    token_score = (
        len(c_tokens & e_tokens)
        / len(union)
        if union
        else 0.0
    )

    var_score = (
        1.0
        if candidate.get("variable_count")
        == existing.get("variable_count")
        else 0.0
    )

    return round(
        0.65 * shape_score
        + 0.25 * token_score
        + 0.10 * var_score,
        4,
    )

def diversity_check(
    candidate: dict,
    recent_descriptors: list[dict],
    threshold: float = 0.92,
    exact_shape_cap: int = 3,
    exact_shape_window: int = 12,
) -> dict:
    """Keep variety without making small/easy buckets impossible to fill.

    Exact descriptor duplicates are rejected immediately. The same operator shape
    may appear a few times because basic aptitude domains legitimately reuse core
    formulas; only over-representation in the recent window is blocked.
    """
    if not recent_descriptors:
        return {
            "accepted": True,
            "max_similarity": 0.0,
            "matched_fingerprint": None,
            "reason": "no_recent_questions",
            "same_shape_recent_count": 0,
        }

    for row in recent_descriptors:
        if candidate.get("fingerprint") and candidate.get("fingerprint") == row.get("fingerprint"):
            return {
                "accepted": False,
                "max_similarity": 1.0,
                "matched_fingerprint": row.get("fingerprint"),
                "reason": "exact_structure_duplicate",
                "same_shape_recent_count": 1,
            }

    window = recent_descriptors[:max(1, int(exact_shape_window))]
    same_shape_rows = [
        row for row in window
        if candidate.get("shape") == row.get("shape")
        and candidate.get("variable_count") == row.get("variable_count")
    ]

    if len(same_shape_rows) >= max(1, int(exact_shape_cap)):
        return {
            "accepted": False,
            "max_similarity": 1.0,
            "matched_fingerprint": same_shape_rows[0].get("fingerprint"),
            "reason": "math_shape_frequency_cap",
            "same_shape_recent_count": len(same_shape_rows),
        }

    best_score = -1.0
    best = None
    for row in recent_descriptors[:30]:
        score = structural_similarity(candidate, row)
        if score > best_score:
            best_score = score
            best = row

    return {
    "accepted": True,
    "max_similarity": round(max(best_score, 0.0), 4),
    "matched_fingerprint": (best or {}).get("fingerprint"),
    "reason": "structurally_distinct",
    "same_shape_recent_count": len(same_shape_rows),
}

# ---------------------------------------------------------------------------
# EXISTING DISTRACTOR GENERATION LOGIC
# ---------------------------------------------------------------------------

def _mutated_expressions(
    expression: str,
):
    """Yield common arithmetic-mistake variants of an expression.

    These are not trusted as solutions. They are only candidate distractors and
    are re-evaluated through the same restricted arithmetic evaluator.
    """

    root = ast.parse(
        expression,
        mode="eval",
    )

    paths = []

    def walk(
        node,
        path=(),
    ):
        if isinstance(
            node,
            ast.BinOp,
        ):
            paths.append(path)

            walk(
                node.left,
                path + ("left",),
            )

            walk(
                node.right,
                path + ("right",),
            )

        elif isinstance(
            node,
            ast.UnaryOp,
        ):
            walk(
                node.operand,
                path + ("operand",),
            )

        elif isinstance(
            node,
            ast.Expression,
        ):
            walk(
                node.body,
                path + ("body",),
            )

    walk(root)

    replacements = {
        ast.Add: (
            ast.Sub,
        ),

        ast.Sub: (
            ast.Add,
        ),

        ast.Mult: (
            ast.Div,
        ),

        ast.Div: (
            ast.Mult,
        ),
    }

    for path in paths:
        target = root

        for part in path:
            target = getattr(
                target,
                part,
            )

        for replacement in replacements.get(
            type(target.op),
            (),
        ):
            mutated = copy.deepcopy(
                root
            )

            node = mutated

            for part in path:
                node = getattr(
                    node,
                    part,
                )

            node.op = replacement()

            ast.fix_missing_locations(
                mutated
            )

            yield ast.unparse(
                mutated.body
            )


def plausible_distractors(
    expression: str,
    variables: dict,
    answer: float,
    count: int = 3,
) -> list[float]:

    candidates: list[float] = []

    def add(value):
        try:
            value = float(value)

        except Exception:
            return

        if (
            not math.isfinite(value)
            or value <= 0
        ):
            return

        tolerance = max(
            1e-7,
            abs(answer) * 1e-7,
        )

        if (
            abs(value - answer)
            <= tolerance
        ):
            return

        if answer > 0:
            ratio = value / answer

            if (
                ratio < 0.2
                or ratio > 5.0
            ):
                return

        if any(
            abs(value - x)
            <= max(
                1e-7,
                abs(x) * 1e-7,
            )
            for x in candidates
        ):
            return

        candidates.append(
            value
        )

    for mutated in _mutated_expressions(
        expression
    ):
        try:
            add(
                evaluate_float(
                    mutated,
                    variables,
                )
            )

        except Exception:
            continue

        if len(candidates) >= count:
            return candidates[:count]

    # Fallbacks model common percent/decimal/rounding mistakes.
    # They are only used if operator-substitution mistakes do not
    # produce enough valid choices.

    for value in (
        answer * 0.9,
        answer * 1.1,
        answer / 10,
        answer * 10,
        answer * 0.5,
        answer * 2,
    ):
        add(value)

        if len(candidates) >= count:
            break

    return candidates[:count]


def validate_distractors(
    answer: float,
    distractors: list[float],
) -> dict:

    if len(distractors) != 3:
        return {
            "accepted": False,
            "reason": (
                "need_three_unique_distractors"
            ),
        }

    if any(
        (
            not math.isfinite(x)
            or x <= 0
        )
        for x in distractors
    ):
        return {
            "accepted": False,
            "reason": (
                "non_positive_or_non_finite_distractor"
            ),
        }

    if len(
        {
            round(x, 9)
            for x in distractors
        }
    ) != 3:
        return {
            "accepted": False,
            "reason": (
                "duplicate_distractor"
            ),
        }

    if any(
        abs(x - answer)
        <= max(
            1e-7,
            abs(answer) * 1e-7,
        )
        for x in distractors
    ):
        return {
            "accepted": False,
            "reason": (
                "distractor_matches_answer"
            ),
        }

    return {
        "accepted": True,
        "reason": (
            "plausible_unique_distractors"
        ),
    }