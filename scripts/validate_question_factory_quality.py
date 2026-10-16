"""Offline validation for deterministic Question Factory quality gates."""

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
from core.ai_expression_engine import evaluate_float, evaluate_decimal


def check_case(name, expr, variables, steps, expected):
    a = evaluate_float(expr, variables)
    b = float(evaluate_decimal(expr, variables))

    assert abs(a - b) <= max(
        1e-7,
        abs(a) * 1e-7,
    ), (name, a, b)

    d = difficulty_features(
        expr,
        variables,
        steps,
    )

    assert d["difficulty"] == expected, (
        name,
        d,
    )

    distractors = plausible_distractors(
        expr,
        variables,
        a,
        3,
    )

    assert validate_distractors(
        a,
        distractors,
    )["accepted"], (
        name,
        distractors,
    )

    return d, distractors


def main():
    # ---------------------------------------------------------
    # EXISTING TESTS
    # ---------------------------------------------------------

    cases = [
        (
            "easy",
            "speed * time",
            {
                "speed": 40,
                "time": 3,
            },
            [
                "Multiply speed by time.",
            ],
            "easy",
        ),

        (
            "medium",
            "(distance / speed_a) + (distance / speed_b)",
            {
                "distance": 120,
                "speed_a": 40,
                "speed_b": 60,
            },
            [
                "Find first travel time.",
                "Find second travel time.",
                "Add the two times.",
            ],
            "medium",
        ),

        (
            "hard",
            "((base * rate / 100) + fee) * (1 + tax / 100) - rebate",
            {
                "base": 800,
                "rate": 12,
                "fee": 25,
                "tax": 18,
                "rebate": 10,
            },
            [
                "Compute the percentage component.",
                "Add the fixed fee.",
                "Apply tax to the subtotal.",
                "Subtract the rebate.",
            ],
            "hard",
        ),
    ]

    for case in cases:
        d, opts = check_case(*case)

        print(
            f"PASS {case[0]} "
            f"score={d['difficulty_score']} "
            f"distractors={opts}"
        )

    # ---------------------------------------------------------
    # EXISTING DIVERSITY TESTS
    # ---------------------------------------------------------

    c1 = structural_descriptor(
        "Time, Speed & Distance",
        "speed * time",
        {
            "speed": 40,
            "time": 3,
        },
        "basic_distance",
        "distance",
    )

    c2 = structural_descriptor(
        "Time, Speed & Distance",
        "velocity * duration",
        {
            "velocity": 55,
            "duration": 2,
        },
        "basic_distance",
        "distance",
    )

    result = diversity_check(
        c2,
        [c1],
    )

    assert not result["accepted"], result

    print(
        "PASS diversity duplicate rejected "
        f"similarity={result['max_similarity']}"
    )

    c3 = structural_descriptor(
        "Time, Speed & Distance",
        "distance / (fast - slow)",
        {
            "distance": 80,
            "fast": 60,
            "slow": 40,
        },
        "catch_up",
        "relative speed",
    )

    result = diversity_check(
        c3,
        [c1],
    )

    assert result["accepted"], result

    print(
        "PASS diversity new structure accepted "
        f"similarity={result['max_similarity']}"
    )

    # ---------------------------------------------------------
    # REGRESSION TEST 1
    # UNUSED NUMERIC VARIABLE MUST BE REJECTED
    # ---------------------------------------------------------

    usage = validate_variable_usage(
        "distance / speed",
        {
            "distance": 120,
            "speed": 60,
            "alice_age": 25,
        },
        (
            "A vehicle travels {distance} km at "
            "{speed} km/h. Alice is "
            "{alice_age} years old."
        ),
    )

    assert not usage["accepted"], usage

    assert usage["reason"] == (
        "unused_variables"
    ), usage

    assert "alice_age" in usage[
        "unused_variables"
    ], usage

    print(
        "PASS unused numeric variable rejected"
    )

    # ---------------------------------------------------------
    # REGRESSION TEST 2
    # INCOMPATIBLE SPEED REFERENCE FRAMES MUST FAIL
    #
    # This reproduces the class of bug found in the old
    # escalator question:
    #
    # bob_run_speed was already relative to the ground,
    # but escalator speed was added to it again.
    # ---------------------------------------------------------

    frames = validate_reference_frames(
        (
            "bob_run_speed + "
            "escalator_reverse_speed"
        ),
        {
            "bob_run_speed": {
                "unit": "m/s",
                "role": "speed",
                "relative_to": "ground",
            },

            "escalator_reverse_speed": {
                "unit": "m/s",
                "role": "speed",
                "relative_to": "escalator",
            },
        },
    )

    assert not frames["accepted"], frames

    assert frames["reason"] == (
        "incompatible_speed_reference_frames"
    ), frames

    print(
        "PASS incompatible speed reference "
        "frames rejected"
    )

    # ---------------------------------------------------------
    # REGRESSION TEST 3
    # SOLUTION PLACEHOLDERS MUST BE RENDERED
    #
    # This reproduces the old:
    # {distance_a}
    # {distance_b}
    # canonical_solution bug.
    # ---------------------------------------------------------

    solution = validate_solution_rendering(
        [
            (
                "Runner A travels {distance_a} "
                "meters per minute."
            ),
            (
                "Runner B travels {distance_b} "
                "meters per minute."
            ),
            (
                "Combined speed = "
                "{distance_a} + {distance_b}."
            ),
        ],
        {
            "distance_a": 120,
            "distance_b": 180,
        },
    )

    assert solution["accepted"], solution

    rendered = " ".join(
        solution["rendered_steps"]
    )

    assert "{distance_a}" not in rendered
    assert "{distance_b}" not in rendered

    assert "120" in rendered
    assert "180" in rendered

    print(
        "PASS solution placeholders rendered"
    )

    # ---------------------------------------------------------
    # REGRESSION TEST 4
    # VALID SAME-REFERENCE-FRAME SPEEDS MUST PASS
    #
    # Example:
    # two cyclists travelling in opposite directions.
    # Both speeds are already ground-relative.
    # ---------------------------------------------------------

    frames = validate_reference_frames(
        "speed_a + speed_b",
        {
            "speed_a": {
                "unit": "km/h",
                "role": "speed",
                "relative_to": "ground",
            },

            "speed_b": {
                "unit": "km/h",
                "role": "speed",
                "relative_to": "ground",
            },
        },
    )

    assert frames["accepted"], frames

    print(
        "PASS compatible ground-relative "
        "speeds accepted"
    )

    # ---------------------------------------------------------
    # REGRESSION TEST 5
    # DETERMINISTIC DIFFICULTY REASSIGNMENT
    #
    # Simulate an admin requesting Hard while the generated
    # expression actually measures as Medium.
    #
    # This is the exact class of behavior observed with the
    # train + mechanical falcon question.
    # ---------------------------------------------------------

    requested_difficulty = "hard"

    reassignment_expr = (
        "speed_falcon * "
        "(total_distance / "
        "(speed_alpha + speed_beta))"
    )

    reassignment_variables = {
        "total_distance": 600,
        "speed_alpha": 40,
        "speed_beta": 60,
        "speed_falcon": 120,
    }

    reassignment_steps = [
        "Find the combined closing speed.",
        "Find the collision time.",
        "The falcon flies for that entire time.",
        "Multiply falcon speed by collision time.",
    ]

    reassignment = difficulty_features(
        reassignment_expr,
        reassignment_variables,
        reassignment_steps,
    )

    actual_difficulty = reassignment[
        "difficulty"
    ]

    assert requested_difficulty == "hard"

    assert actual_difficulty == "medium", (
        reassignment
    )

    assert (
        actual_difficulty
        != requested_difficulty
    )

    print(
        "PASS difficulty reassignment "
        f"requested={requested_difficulty} "
        f"actual={actual_difficulty}"
    )

    # ---------------------------------------------------------
    # REGRESSION TEST 6
    # REASSIGNED QUESTION MUST BE CHECKED AGAINST
    # ITS DESTINATION DIFFICULTY BUCKET
    #
    # We simulate an existing Medium question having the
    # same mathematical structure as the reassigned question.
    # ---------------------------------------------------------

    existing_medium = structural_descriptor(
        "Time, Speed & Distance",
        (
            "bird_speed * "
            "(separation / "
            "(train_a_speed + train_b_speed))"
        ),
        {
            "separation": 500,
            "train_a_speed": 50,
            "train_b_speed": 50,
            "bird_speed": 100,
        },
        "continuous_interception_distance",
        "relative motion & interceptions",
    )

    reassigned_descriptor = (
        structural_descriptor(
            "Time, Speed & Distance",
            reassignment_expr,
            reassignment_variables,
            "continuous_interception_distance",
            "relative motion & interceptions",
        )
    )

    destination_diversity = diversity_check(
        reassigned_descriptor,
        [existing_medium],
    )

    assert not destination_diversity[
        "accepted"
    ], destination_diversity

    print(
        "PASS reassigned destination-bucket "
        "duplicate rejected "
        f"similarity="
        f"{destination_diversity['max_similarity']}"
    )

    # ---------------------------------------------------------
    # REGRESSION TEST 7
    # A DIFFERENT REASSIGNED MEDIUM STRUCTURE SHOULD PASS
    # ---------------------------------------------------------

    different_medium = structural_descriptor(
        "Time, Speed & Distance",
        (
            "(distance_a / speed_a) + "
            "(distance_b / speed_b)"
        ),
        {
            "distance_a": 100,
            "speed_a": 50,
            "distance_b": 120,
            "speed_b": 60,
        },
        "two_leg_travel_time",
        "travel time",
    )

    destination_diversity = diversity_check(
        different_medium,
        [existing_medium],
    )

    assert destination_diversity[
        "accepted"
    ], destination_diversity

    print(
        "PASS different destination-bucket "
        "structure accepted "
        f"similarity="
        f"{destination_diversity['max_similarity']}"
    )
        # ---------------------------------------------------------
    # REGRESSION TEST 8
    # VALID STORY CONSTRAINTS MUST PASS
    # ---------------------------------------------------------

    valid_variables = {
        "speed_a": 60,
        "speed_b": 40,
        "meeting_time": 5,
        "distance_a": 300,
        "distance_b": 200,
        "total_distance": 500,
    }

    valid_constraints = [
        {
            "left": "speed_a * meeting_time",
            "operator": "==",
            "right": "distance_a",
        },
        {
            "left": "speed_b * meeting_time",
            "operator": "==",
            "right": "distance_b",
        },
        {
            "left": "distance_a + distance_b",
            "operator": "==",
            "right": "total_distance",
        },
    ]

    constraint_result = validate_constraints(
        valid_constraints,
        valid_variables,
    )

    assert constraint_result["accepted"], (
        constraint_result
    )

    assert (
        constraint_result["constraint_count"] == 3
    )

    print(
        "PASS valid story constraints accepted"
    )

    # ---------------------------------------------------------
    # REGRESSION TEST 9
    # BAD 675-KM TRAIN QUESTION MUST BE REJECTED
    #
    # Original generated question:
    #
    # Alpha = 60 km/h
    # Beta  = 40 km/h
    # Alpha supposedly travelled 50 km more at meeting.
    # Alpha takes 4.1666 h after meeting.
    # Beta takes 9.375 h after meeting.
    #
    # The post-meeting times imply incompatible
    # pre-meeting distances.
    # ---------------------------------------------------------

    bad_train_variables = {
        "speed_alpha": 60,
        "speed_beta": 40,
        "distance_excess": 50,
        "time_alpha": 4.1666,
        "time_beta": 9.375,
    }

    bad_train_constraints = [
        {
            # Alpha's post-meeting distance equals
            # Beta's pre-meeting distance.
            "left": "speed_alpha * time_alpha",
            "operator": "==",

            # Beta's post-meeting distance equals
            # Alpha's pre-meeting distance.
            #
            # From the claimed excess:
            #
            # alpha_pre = beta_pre + distance_excess
            "right": (
                "speed_beta * time_beta "
                "- distance_excess"
            ),
        },
    ]

    constraint_result = validate_constraints(
        bad_train_constraints,
        bad_train_variables,
    )

    assert not constraint_result["accepted"], (
        constraint_result
    )

    assert constraint_result["reason"] == (
        "constraint_not_satisfied"
    ), constraint_result

    print(
        "PASS inconsistent 675-km train "
        "question rejected"
    )

    # ---------------------------------------------------------
    # REGRESSION TEST 10
    # UNKNOWN CONSTRAINT VARIABLES MUST FAIL
    # ---------------------------------------------------------

    unknown_constraint = validate_constraints(
        [
            {
                "left": "speed * mystery_time",
                "operator": "==",
                "right": "distance",
            }
        ],
        {
            "speed": 60,
            "distance": 120,
        },
    )

    assert not unknown_constraint["accepted"], (
        unknown_constraint
    )

    assert unknown_constraint["reason"] == (
        "constraint_unknown_variables"
    )

    assert "mystery_time" in unknown_constraint[
        "unknown_variables"
    ]

    print(
        "PASS unknown constraint variable rejected"
    )


 
    # ---------------------------------------------------------
    # FINAL
    # ---------------------------------------------------------

    print(
        "PASS: Question Factory deterministic "
        "quality gates and regression tests "
        "validated offline."
    )


if __name__ == "__main__":
    main()