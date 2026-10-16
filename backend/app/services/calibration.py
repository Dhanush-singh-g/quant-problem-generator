"""Exploratory first-exposure accuracy; never silently relabel curated models."""
from sqlalchemy import text

MIN_RESPONSES = 30


def calibration(db, limit=50):
    rows = db.execute(text("""
        WITH responses AS (
            SELECT a.user_id, a.id, a.created_at,
                   item->>'question_id' AS question_id,
                   COALESCE((item->>'correct')::boolean, false) AS correct
            FROM quiz_attempts a CROSS JOIN LATERAL json_array_elements(a.details) item
            WHERE COALESCE(item->>'mode', 'unseen') = 'unseen'
        ), first_responses AS (
            SELECT DISTINCT ON (user_id, question_id) user_id, question_id, correct
            FROM responses ORDER BY user_id, question_id, created_at, id
        )
        SELECT q.id, q.domain, q.difficulty, COUNT(r.user_id) AS responses,
               AVG(CASE WHEN r.user_id IS NOT NULL THEN r.correct::int END) AS accuracy
        FROM questions q LEFT JOIN first_responses r ON r.question_id = q.id
        WHERE q.active = true AND q.review_status = 'approved'
        GROUP BY q.id, q.domain, q.difficulty
        ORDER BY COUNT(r.user_id) DESC, q.id LIMIT :limit
    """), {"limit": limit}).mappings().all()
    items = []
    for row in rows:
        accuracy = float(row["accuracy"]) if row["accuracy"] is not None else None
        observed = "insufficient_data" if row["responses"] < MIN_RESPONSES else (
            "easy" if accuracy >= .75 else "hard" if accuracy < .4 else "medium")
        items.append({"question_id": row["id"], "domain": row["domain"], "curated_difficulty": row["difficulty"],
                      "first_exposures": row["responses"], "accuracy": round(accuracy * 100, 1) if accuracy is not None else None,
                      "observed_band": observed})
    return {"minimum_responses": MIN_RESPONSES, "items": items,
            "method": "First submitted unseen response per user/item; omissions count as incorrect. Revision is excluded. Exploratory only."}
