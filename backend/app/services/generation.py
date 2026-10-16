import hashlib
import json
import random
import sys
import time
from pathlib import Path
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..models import Question, QuestionAssignment

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.cs_question_engine import build_cs_question, domains as cs_domains, difficulties_for as cs_difficulties
from agents.difficulty_agent import classify_difficulty
from agents.solver_agent_a import solve_a
from agents.solver_agent_b import solve_b
from agents.validator_agent import validate_answers
from agents.cs_validator import validate_cs_question
from services.question_designer import redesign_batch
from core.model_registry import generate_model_question, MODELS
from services.model_validation import validate_model_question
from .generation_metrics import incr as metric_incr, record_rejection, record_latency
from ..core.config import settings

RULES = json.loads((ROOT / "data/design_rules.json").read_text(encoding="utf-8"))
VALID_DIFFICULTIES = {"easy", "medium", "hard", "ALL"}
APTITUDE_DOMAINS = list(RULES["templates"].keys())
CS_DOMAINS = cs_domains()


def all_domains():
    return [*APTITUDE_DOMAINS, *CS_DOMAINS]


def domain_categories():
    return {
        "Quantitative Aptitude": APTITUDE_DOMAINS,
        "Computer Science Fundamentals": CS_DOMAINS,
    }


def _candidate_templates(domain: str = "ALL", difficulty: str = "ALL"):
    """Return only templates that genuinely implement the requested difficulty."""
    return [(dom, template) for dom, template in MODELS.values()
            if (domain == "ALL" or dom == domain)
            and (difficulty == "ALL" or template["difficulty"] == difficulty)]



def _build_candidate(domain: str, difficulty: str):
    if domain in CS_DOMAINS:
        return build_cs_question(domain, difficulty)
    if difficulty != "ALL":
        return generate_model_question(domain, difficulty)
    candidates = _candidate_templates(domain, difficulty)
    if not candidates:
        raise ValueError("no deterministic template for requested domain/difficulty")
    dom, template = random.choice(candidates)
    q = generate_model_question(dom, template["difficulty"], template["template_id"])
    q.setdefault("generation_metadata", {})
    q["generation_metadata"]["difficulty_source"] = "difficulty_specific_template"
    return q


def _build_any_candidate(domain: str, difficulty: str):
    if domain != "ALL":
        return _build_candidate(domain, difficulty)

    compatible = [d for d, bands in domain_difficulty_map().items() if difficulty == "ALL" or difficulty in bands]
    if not compatible:
        raise ValueError("no domain supports requested difficulty")
    return _build_candidate(random.choice(compatible), difficulty)



def _question_fingerprint(q: dict) -> str:
    """Stable logical duplicate key used across concurrent generator workers."""
    meta = q.get("generation_metadata", {})
    family = meta.get("question_family", "quantitative")
    if family == "quantitative":
        payload = {
            "family": family,
            "domain": q.get("domain"),
            "template": meta.get("template_used"),
            "structure": meta.get("structure_signature") or meta.get("answer_expression"),
            "variables": {k: v for k, v in q.get("variables", {}).items()
                          if isinstance(v, (int, float)) and not isinstance(v, bool)},
        }
    else:
        # AI context is deliberately excluded from identity so the same
        # canonical CS item cannot bypass deduplication through paraphrased context.
        payload = {
            "family": family,
            "domain": q.get("domain"),
            "fact_id": meta.get("fact_id"),
        }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_one_ai_question(db: Session, domain: str, difficulty: str, *, commit: bool = True):
    """Publish supported models, never AI formulas.

    With commit=False, the caller commits the question with its durable job
    outcome. Optional AI context failure cannot invalidate a correct model.
    """
    started = time.perf_counter()
    metric_incr("requested")
    total_ai_calls = 0
    try:
        if domain not in all_domains() or difficulty not in domain_difficulty_map().get(domain, []):
            return {"generated": 0, "reason": "unsupported_model_bucket"}
        for attempt in range(1, max(1, settings.generation_quality_attempts) + 1):
            q = _build_candidate(domain, difficulty)
            q.update(classify_difficulty(q))
            meta = {"source": "disabled", "api_calls": 0}
            verification = validate_model_question(q)
            fingerprint = _question_fingerprint(q)
            if db.scalar(select(Question.id).where(Question.content_hash == fingerprint)):
                metric_incr("duplicate")
                continue
            if settings.generation_use_ai_context:
                designed, meta = redesign_batch([q])
                q = designed[0]
                total_ai_calls += int(meta.get("api_calls", 0) or 0)
                verification = validate_model_question(q)
            row = Question(
                review_status="approved", id=q["id"], domain=q["domain"], difficulty=q["difficulty"], story_text=q["story_text"],
                options=q["options"], correct_option=q["correct_option"], canonical_solution=q["canonical_solution"],
                answer_value=str(q["answer_value"]), answer_unit=q["answer_unit"], variables=q["variables"],
                content_hash=fingerprint, generation_metadata={
                    **q["generation_metadata"], "ai_source": meta.get("source"),
                    "verification": verification, "quality_status": "validated",
                },
            )
            try:
                with db.begin_nested():
                    db.add(row)
                    db.flush()
            except IntegrityError as exc:
                if getattr(exc.orig, "sqlstate", None) != "23505":
                    raise
                metric_incr("duplicate")
                continue
            if commit:
                db.commit()
            metric_incr("accepted")
            return {"generated": 1, "question_id": row.id, "ai_calls": total_ai_calls,
                    "requested_difficulty": difficulty, "stored_difficulty": row.difficulty,
                    "quality_status": "validated", "ai_source": meta.get("source")}
        record_rejection("duplicate")
        return {"generated": 0, "reason": "duplicate", "ai_calls": total_ai_calls}
    finally:
        record_latency(time.perf_counter() - started)


def generate_questions(
    db: Session,
    count: int = 10,
    domain: str = "ALL",
    use_ai: bool = True,
    difficulty: str = "ALL",
):
    """Generate validated questions with an optional Gemini context prefix.

    Quantitative questions: deterministic templates/formulas own structure,
    numbers, answer and options. CS questions: the curated fact bank owns truth,
    answer and distractors. Gemini can add only a semantically neutral prefix;
    the canonical question stem remains immutable.
    """
    difficulty = difficulty.lower() if difficulty != "ALL" else "ALL"
    if difficulty not in VALID_DIFFICULTIES:
        return {"generated": 0, "ai_calls": 0, "ai_source": "disabled", "reason": "invalid_difficulty"}
    if domain != "ALL" and domain not in all_domains():
        return {"generated": 0, "ai_calls": 0, "ai_source": "disabled", "reason": "unknown_domain"}
    if difficulty != "ALL" and difficulty not in domain_difficulty_map().get(domain, []) and domain != "ALL":
        return {"generated": 0, "ai_calls": 0, "ai_source": "disabled", "reason": "domain_does_not_support_difficulty"}

    built = []
    attempts = 0
    while len(built) < count and attempts < max(20, count * 5):
        attempts += 1
        try:
            q = _build_any_candidate(domain, difficulty)
            q.update(classify_difficulty(q))
            if difficulty != "ALL" and q["difficulty"] != difficulty:
                continue
            built.append(q)
        except (ValueError, RuntimeError):
            continue

    meta = {"source": "disabled", "api_calls": 0, "accepted": 0}
    if use_ai and settings.generation_use_ai_context and built:
        built, meta = redesign_batch(built)

    saved = []
    rejected = 0
    for q in built:
        family = q.get("generation_metadata", {}).get("question_family", "quantitative")
        if family == "computer_science":
            val = validate_cs_question(q)
            verification = {
                "mode": "deterministic_fact_bank",
                "validator": val,
            }
        else:
            a = solve_a(q)
            b = solve_b(q)
            val = validate_answers(q, a, b)
            verification = {
                "mode": "dual_deterministic_solver",
                "solver_a_confidence": a.get("confidence", 0),
                "solver_b_confidence": b.get("confidence", 0),
                "validator": val,
            }

        if val["final_validation"] != "valid":
            rejected += 1
            continue

        verification = validate_model_question(q)
        fingerprint = _question_fingerprint(q)
        if db.scalar(select(Question.id).where(Question.content_hash == fingerprint)):
            rejected += 1
            continue

        row = Question(
            review_status="approved",
            id=q["id"],
            domain=q["domain"],
            difficulty=q["difficulty"],
            story_text=q["story_text"],
            options=q["options"],
            correct_option=q["correct_option"],
            canonical_solution=q["canonical_solution"],
            answer_value=str(q["answer_value"]),
            answer_unit=q["answer_unit"],
            variables=q["variables"],
            content_hash=fingerprint,
            generation_metadata={
                **q["generation_metadata"],
                "ai_source": meta.get("source"),
                "target_difficulty": difficulty,
                "quality_status": "validated",
                "verification": verification,
            },
        )
        try:
            # Nested transaction makes duplicate races harmless when multiple Celery
            # workers generate the same logical question concurrently.
            with db.begin_nested():
                db.add(row)
                db.flush()
            saved.append(row)
        except IntegrityError:
            rejected += 1

    db.commit()
    return {
        "generated": len(saved),
        "rejected": rejected,
        "ai_calls": meta.get("api_calls", 0),
        "ai_source": meta.get("source"),
        "ai_structures_accepted": meta.get("accepted", 0),
    }


def pool_count(db: Session, domain: str = "ALL", difficulty: str = "ALL", unused_only: bool = False):
    stmt = select(func.count()).select_from(Question).where(Question.active.is_(True), Question.review_status == "approved")
    if unused_only:
        stmt = stmt.outerjoin(QuestionAssignment, QuestionAssignment.question_id == Question.id).where(
            QuestionAssignment.id.is_(None)
        )
    if domain != "ALL":
        stmt = stmt.where(Question.domain == domain)
    if difficulty != "ALL":
        stmt = stmt.where(Question.difficulty == difficulty.lower())
    return db.scalar(stmt) or 0


def domain_difficulty_map():
    order = {"easy": 0, "medium": 1, "hard": 2}
    out = {}
    for domain in APTITUDE_DOMAINS:
        bands = {str(t.get("difficulty", "medium")).lower() for t in RULES["templates"].get(domain, [])}
        out[domain] = sorted(bands, key=lambda x: order.get(x, 99))
    for domain in CS_DOMAINS:
        out[domain] = cs_difficulties(domain)
    return out
