"""Idempotent, offline starter inventory; run explicitly during local setup."""
import argparse
from sqlalchemy import select, func
from .core.db import SessionLocal
from .models import Question
from .services.generation import generate_questions, all_domains, domain_difficulty_map
from core.cs_question_engine import FACTS


def seed(db, per_bucket=10):
    generated = 0
    for domain in all_domains():
        for band in domain_difficulty_map()[domain]:
            target = min(per_bucket, sum(f["difficulty"] == band for f in FACTS[domain])) if domain in FACTS else per_bucket
            # Existing approved inventory counts toward the target; rerunning never resets it.
            for _ in range(8):
                current = db.scalar(select(func.count()).select_from(Question).where(
                    Question.domain == domain, Question.difficulty == band,
                    Question.active.is_(True), Question.review_status == "approved")) or 0
                if current >= target:
                    break
                result = generate_questions(db, target - current, domain, False, band)
                generated += result["generated"]
    return generated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-bucket", type=int, default=10, choices=range(1, 101))
    args = parser.parse_args()
    with SessionLocal() as db:
        print({"new_validated_questions": seed(db, args.per_bucket), "ai_calls": 0})
