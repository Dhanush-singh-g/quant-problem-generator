import json
import random
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACTS = json.loads((ROOT / "data" / "cs_concepts.json").read_text(encoding="utf-8"))
LETTERS = ["A", "B", "C", "D"]

PATTERNS = {
    "easy": [
        "Which statement about {skill} is correct?",
        "A developer is reviewing {skill}. Which statement is accurate?",
        "Choose the correct description of {skill}.",
    ],
    "medium": [
        "During a technical review involving {skill}, which statement should the engineer rely on?",
        "A team is making a design decision about {skill}. Which option is technically correct?",
        "Which statement best explains the behavior of {skill}?",
    ],
    "hard": [
        "An engineer is debugging a production issue related to {skill}. Which principle is the safest technical conclusion?",
        "Which statement captures the important constraint or trade-off involving {skill}?",
        "In a system-design discussion involving {skill}, which statement is correct?",
    ],
}


def domains():
    return list(FACTS.keys())


def difficulties_for(domain: str):
    order = {"easy": 0, "medium": 1, "hard": 2}
    return sorted({row["difficulty"] for row in FACTS.get(domain, [])}, key=lambda x: order[x])


def fact_by_id(fact_id: str):
    for domain, rows in FACTS.items():
        for row in rows:
            if row["id"] == fact_id:
                return domain, row
    return None, None


def build_cs_question(domain: str, difficulty: str = "ALL"):
    rows = FACTS.get(domain, [])
    if difficulty != "ALL":
        rows = [row for row in rows if row["difficulty"] == difficulty]
    if not rows:
        raise ValueError(f"No CS facts available for {domain} / {difficulty}")

    fact = random.choice(rows)
    option_texts = [fact["correct_answer"], *fact["distractors"]]
    random.shuffle(option_texts)
    options = dict(zip(LETTERS, option_texts))
    correct_option = next(k for k, value in options.items() if value == fact["correct_answer"])
    story = random.choice(PATTERNS[fact["difficulty"]]).format(skill=fact["skill"])

    return {
        "id": str(uuid.uuid4()),
        "domain": domain,
        "story_text": story,
        "options": options,
        "correct_option": correct_option,
        "canonical_solution": f"{fact['correct_answer']} {fact['fact']}",
        "answer_value": fact["correct_answer"],
        "answer_unit": "concept",
        "variables": {},
        "generation_metadata": {
            "question_family": "computer_science",
            "truth_source": "curated_fact",
            "model_version": 1,
            "fact_id": fact["id"],
            "skill": fact["skill"],
            "fact": fact["fact"],
            "template_used": fact["id"],
            "declared_difficulty": fact["difficulty"],
            "method": "curated_fact_plus_generated_structure",
        },
    }
