"""Review existing inventory without deleting questions or attempt history.

Run in maintenance mode with workers stopped: python -m app.audit_inventory --apply
Without --apply this is a read-only report. Unsupported/invalid questions are
quarantined; supported valid items receive the current logical identity.
"""
import argparse
from collections import Counter

from sqlalchemy import select, text
from .core.db import SessionLocal
from .models import Question
from .services.generation import _question_fingerprint
from services.model_validation import validate_model_question


def audit(db, apply=False):
    if apply:
        db.execute(text("SELECT pg_advisory_xact_lock(728419003)"))
    rows = list(db.scalars(select(Question).order_by(Question.created_at, Question.id)
                           .with_for_update() if apply else select(Question).order_by(Question.created_at, Question.id)).all())
    report = Counter()
    plans = []
    identities = set()
    for row in rows:
        q = {key: getattr(row, key) for key in (
            "id", "domain", "difficulty", "story_text", "options", "correct_option",
            "canonical_solution", "answer_value", "answer_unit", "variables", "generation_metadata",
        )}
        try:
            verification = validate_model_question(q)
            identity = _question_fingerprint(q)
            state = "duplicate" if identity in identities else "approved"
            identities.add(identity)
        except (ValueError, TypeError, KeyError, ArithmeticError):
            state, identity, verification = "quarantined", None, None
        report[state] += 1
        plans.append((row, state, identity, verification))
    if apply:
        # Clear old identities first so swapping owners cannot violate uniqueness.
        # All changes commit atomically; referenced questions remain available in reviews.
        for row, *_ in plans:
            row.content_hash = None
        db.flush()
        for row, state, identity, verification in plans:
            row.review_status = state
            if state != "approved":
                row.active = False
            else:
                row.content_hash = identity
                row.generation_metadata = {**row.generation_metadata, "verification": verification,
                                           "quality_status": "validated"}
        db.commit()
    return dict(report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        print({"applied": args.apply, "inventory": audit(db, args.apply)})
