import random
import time
import uuid
import hashlib
import hmac
import math
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.config import settings
from ..core.auth import hash_password, verify_password, create_token, current_user, admin_user
from ..models import (
    Question, QuizAttempt, QuizSession, QuestionAssignment, User,
    Assessment, AssessmentSession, AssessmentQuestionAssignment,
    AssessmentVariant, AssessmentVariantQuestion, UserQuestionHistory,
)
from ..schemas import *
from ..services.cache import (
    record_pool_shortage,
    record_quiz_started,
    record_replenish_requested, record_variant_collision,
    redis_stats, redis_ready, rate_limit,
)
from ..services.generation import RULES, domain_difficulty_map, all_domains, domain_categories

router = APIRouter(prefix="/api")
VALID_DIFFICULTIES = {"easy", "medium", "hard", "ALL"}


@router.get("/health")
@router.get("/health/live")
def health():
    """Liveness: the API process is running."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(db: Session = Depends(get_db)):
    """Readiness for load balancers: durable DB and distributed Redis are reachable."""
    db_ok = False
    try:
        db.execute(select(User.id).limit(1)).first()
        db_ok = True
    except Exception:
        db.rollback()
    redis_ok = redis_ready()
    payload = {"status": "ready" if db_ok and redis_ok else "not_ready", "database": db_ok, "redis": redis_ok}
    if not (db_ok and redis_ok):
        return JSONResponse(payload, status_code=503)
    return payload


@router.get("/domains")
def domains():
    return {"domains": all_domains(), "categories": domain_categories()}


def _set_auth_cookie(response: Response, token: str):
    response.set_cookie(
        settings.auth_cookie_name, token, httponly=True, secure=settings.cookie_secure,
        samesite=settings.cookie_samesite, max_age=settings.jwt_expire_minutes * 60, path="/",
    )


def _auth_limit(request: Request, identity: str | None = None):
    host = request.client.host if request.client else "unknown"
    if not rate_limit(f"auth-ip:{host}", settings.auth_rate_limit_per_minute):
        raise HTTPException(429, "Too many authentication attempts. Try again shortly.")
    if identity:
        # Hash the identifier so raw email addresses are not placed in Redis keys.
        ident = hashlib.sha256(identity.lower().strip().encode()).hexdigest()[:24]
        if not rate_limit(f"auth-account:{ident}", settings.account_auth_rate_limit_per_minute):
            raise HTTPException(429, "Too many authentication attempts for this account. Try again shortly.")


@router.post("/auth/register", response_model=AuthResponse)
def register(body: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    _auth_limit(request)
    email = body.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password), role="user")
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        # Covers concurrent registrations that raced after the pre-check.
        raise HTTPException(409, "Email already registered")
    token = create_token(user); _set_auth_cookie(response, token)
    return {"user": user}


@router.post("/auth/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    _auth_limit(request, email)
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if not user.password_hash.startswith("$argon2"):
        user.password_hash = hash_password(body.password)
        db.commit()
    token = create_token(user); _set_auth_cookie(response, token)
    return {"user": user}


@router.post("/auth/google", response_model=AuthResponse)
def google_login(body: GoogleLoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    _auth_limit(request)
    if not settings.google_client_id:
        raise HTTPException(503, "Google sign-in is not configured")
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        info = id_token.verify_oauth2_token(body.credential, google_requests.Request(), settings.google_client_id)
    except Exception:
        raise HTTPException(401, "Invalid Google credential")
    if not info.get("email") or not info.get("email_verified") or not info.get("sub"):
        raise HTTPException(401, "Google account email is not verified")
    email = str(info["email"]).lower().strip()
    sub = str(info["sub"])
    user = db.scalar(select(User).where(User.google_sub == sub))
    if not user:
        user = db.scalar(select(User).where(User.email == email))
        if user:
            if user.google_sub and user.google_sub != sub:
                raise HTTPException(409, "This email is already linked to a different Google identity")
            if user.role == "admin" and not user.google_sub:
                raise HTTPException(403, "Google auto-linking is disabled for administrator accounts")
            user.google_sub = sub
        else:
            user = User(
                email=email,
                name=str(info.get("name") or email.split("@")[0])[:120],
                password_hash=hash_password(uuid.uuid4().hex + uuid.uuid4().hex),
                google_sub=sub,
                role="user",
            )
            db.add(user)
        try:
            db.commit(); db.refresh(user)
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Account linking changed concurrently. Please sign in again.")
    token = create_token(user); _set_auth_cookie(response, token)
    return {"user": user}


@router.post("/auth/logout")
def logout(response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.execute(update(User).where(User.id == user.id).values(token_version=User.token_version + 1))
    db.commit()
    response.delete_cookie(
        settings.auth_cookie_name, path="/", secure=settings.cookie_secure, samesite=settings.cookie_samesite
    )
    return {"ok": True}


@router.get("/auth/me", response_model=UserPublic)
def me(user: User = Depends(current_user)):
    return user


@router.get("/admin/question-factory/inventory")
def question_factory_inventory(db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    rows = db.execute(
        select(Question.domain, Question.difficulty, func.count(Question.id))
        .where(Question.active.is_(True), Question.review_status == "approved")
        .group_by(Question.domain, Question.difficulty)
    ).all()
    counts = {(domain, difficulty): int(count) for domain, difficulty, count in rows}
    inventory = []
    for domain in all_domains():
        for difficulty in ("easy", "medium", "hard"):
            if difficulty in domain_difficulty_map().get(domain, []):
                inventory.append({"domain": domain, "difficulty": difficulty, "count": counts.get((domain, difficulty), 0)})
    return {"inventory": inventory}


@router.get("/admin/question-factory/calibration")
def question_calibration(limit: int = Query(50, ge=1, le=200),
                         db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    from ..services.calibration import calibration
    return calibration(db, limit)


@router.post("/admin/question-factory/generate", status_code=202)
def manual_question_factory_generate(
    body: ManualGenerationRequest, db: Session = Depends(get_db), admin: User = Depends(admin_user)
):
    """Persist every requested job before notifying the workers."""
    if body.domain not in all_domains():
        raise HTTPException(400, "Unknown domain")
    if body.difficulty not in domain_difficulty_map().get(body.domain, []):
        raise HTTPException(400, "Difficulty is not supported for this domain")
    from ..services.generation_batches import create_batch, batch_progress
    from ..workers.tasks import dispatch_generation_jobs
    batch = create_batch(db, admin.id, body.domain, body.difficulty, body.count)
    notified = True
    try:
        dispatch_generation_jobs.delay()
    except Exception:
        notified = False
    return {"batch": batch_progress(db, batch), "worker_notified": notified}


@router.get("/admin/question-factory/batches")
def generation_batches(limit: int = Query(20, ge=1, le=100),
                       db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    from ..models import GenerationBatch
    from ..services.generation_batches import batch_progress
    rows = db.scalars(select(GenerationBatch).order_by(GenerationBatch.created_at.desc()).limit(limit)).all()
    return {"batches": [batch_progress(db, row) for row in rows]}


@router.get("/admin/question-factory/batches/{batch_id}")
def generation_batch(batch_id: str, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    from ..models import GenerationBatch
    from ..services.generation_batches import batch_progress
    batch = db.get(GenerationBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "Generation batch not found")
    return batch_progress(db, batch)


@router.get("/admin/metrics")
def metrics(db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    from services.ai_gateway import gateway
    from ..services.generation_metrics import snapshot as generation_metrics_snapshot

    qcount = db.scalar(select(func.count()).select_from(Question)) or 0
    active_qcount = db.scalar(select(func.count()).select_from(Question).where(Question.active.is_(True), Question.review_status == "approved")) or 0
    legacy_sessions = db.scalar(select(func.count()).select_from(QuizSession)) or 0
    assessment_sessions = db.scalar(select(func.count()).select_from(AssessmentSession)) or 0
    sessions = legacy_sessions + assessment_sessions
    legacy_attempts = db.scalar(select(func.count()).select_from(QuizAttempt)) or 0
    assessment_attempts = db.scalar(
        select(func.count()).select_from(AssessmentSession).where(AssessmentSession.status == "submitted")
    ) or 0
    attempts = legacy_attempts + assessment_attempts
    users = db.scalar(select(func.count()).select_from(User)) or 0
    enhanced = db.scalar(
        select(func.count()).select_from(Question).where(
            Question.generation_metadata["ai_enhanced"].as_boolean().is_(True)
        )
    ) or 0

    shared_redis = redis_stats()
    return {
        "users": users,
        "questions": qcount,
        "active_questions": active_qcount,
        "quiz_sessions": sessions,
        "attempts": attempts,
        "ai_enhanced_questions": enhanced,
        "ai_gateway": {
            "process_api_calls": gateway.api_calls,
            "shared_api_calls": shared_redis.get("ai_api_calls", 0),
            "circuit": "open" if time.time() < gateway.open_until else "closed",
            "consecutive_failures": gateway.failures,
            "available": gateway.available,
        },
        "redis": shared_redis,
        "question_factory": generation_metrics_snapshot(),
        "pool_floor": settings.question_pool_floor,
        "generation_max_pending_per_bucket": settings.generation_max_pending_per_bucket,
    }

# ---------------------------------------------------------------------------
# Admin-managed assessments
# ---------------------------------------------------------------------------

def _variant_count(expected_candidates: int, candidates_per_variant: int) -> int:
    raw = math.ceil(expected_candidates / max(1, candidates_per_variant))
    return max(1, min(settings.max_assessment_variants, raw))


def _assessment_public(row: Assessment):
    return {
        "id": row.id,
        "title": row.title,
        "duration_minutes": row.duration_minutes,
        "easy_count": row.easy_count,
        "medium_count": row.medium_count,
        "hard_count": row.hard_count,
        "domains": row.domains or [],
        "status": row.status,
        "total_questions": row.easy_count + row.medium_count + row.hard_count,
        "expected_candidates": row.expected_candidates,
        "candidates_per_variant": row.candidates_per_variant,
        "variant_count": row.variant_count,
        "blueprint": row.blueprint or [],
    }


def _stable_order(items: list[str], salt: str) -> list[str]:
    return sorted(items, key=lambda x: hashlib.sha256(f"{salt}:{x}".encode()).hexdigest())


def _band_plan(domains: list[str], difficulty: str, count: int, salt: str = ""):
    """Balanced, deterministic topic quota for a difficulty band."""
    if count <= 0:
        return []
    capabilities = domain_difficulty_map()
    compatible = [d for d in domains if difficulty in capabilities.get(d, [])]
    if not compatible:
        return []
    compatible = _stable_order(compatible, f"{salt}:{difficulty}")
    base, remainder = divmod(count, len(compatible))
    return [
        (domain, base + (1 if i < remainder else 0))
        for i, domain in enumerate(compatible)
        if base + (1 if i < remainder else 0) > 0
    ]


def _build_blueprint(domains: list[str], easy: int, medium: int, hard: int, seed: str):
    slots = []
    position = 1
    for difficulty, count in (("easy", easy), ("medium", medium), ("hard", hard)):
        for domain, quota in _band_plan(domains, difficulty, count, seed):
            for _ in range(quota):
                slots.append({"position": position, "domain": domain, "difficulty": difficulty})
                position += 1
    return slots


def _blueprint_seed(title: str, domains: list[str], easy: int, medium: int, hard: int) -> str:
    raw = "|".join([title.strip().lower(), *sorted(domains), str(easy), str(medium), str(hard)])
    return hashlib.sha256(raw.encode()).hexdigest()


def _pool_for_slot(db: Session, domain: str, difficulty: str, target: int) -> list[Question]:
    """Fetch a small indexed candidate pool. Avoid ORDER BY random() on large tables."""
    rows = list(db.scalars(
        select(Question)
        .where(
            Question.active.is_(True),
            Question.review_status == "approved",
            Question.domain == domain,
            Question.difficulty == difficulty,
        )
        .order_by(Question.created_at.desc())
        .limit(max(target, settings.min_question_choices_per_slot))
    ).all())
    return rows


def _ensure_slot_pool(db: Session, domain: str, difficulty: str, desired: int, hard_minimum: int = 1) -> list[Question]:
    rows = _pool_for_slot(db, domain, difficulty, desired)
    if len(rows) < desired:
        record_pool_shortage()

    if len(rows) < hard_minimum:
        raise HTTPException(503, f"Question pool is insufficient for {domain} / {difficulty}. An administrator must generate more inventory.")
    return rows


def _deterministic_index(secret: str, value: str, modulo: int) -> int:
    digest = hmac.new(secret.encode(), value.encode(), hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big") % modulo


def _prepare_variants(db: Session, assessment: Assessment):
    """Materialize reusable paper variants from the stored assessment blueprint."""
    if not assessment.blueprint:
        raise HTTPException(400, "Assessment blueprint is empty")

    variant_ids = list(db.scalars(select(AssessmentVariant.id).where(AssessmentVariant.assessment_id == assessment.id)).all())
    if variant_ids:
        db.execute(delete(AssessmentVariantQuestion).where(AssessmentVariantQuestion.variant_id.in_(variant_ids)))
        db.execute(delete(AssessmentVariant).where(AssessmentVariant.assessment_id == assessment.id))
        db.flush()

    secret = settings.assignment_secret or settings.jwt_secret
    slot_counts: dict[tuple[str, str], int] = {}
    for slot in assessment.blueprint:
        key = (slot["domain"], slot["difficulty"])
        slot_counts[key] = slot_counts.get(key, 0) + 1

    slot_pools: dict[tuple[str, str], list[Question]] = {}
    diversity_target = max(
        settings.min_question_choices_per_slot,
        min(20, max(1, math.ceil(math.sqrt(max(1, assessment.variant_count)))) * 2),
    )
    for key, occurrences in slot_counts.items():
        desired = max(occurrences, diversity_target)
        slot_pools[key] = _ensure_slot_pool(db, key[0], key[1], desired, hard_minimum=occurrences)

    signatures: set[str] = set()
    for variant_number in range(assessment.variant_count):
        variant = AssessmentVariant(assessment_id=assessment.id, variant_number=variant_number)
        db.add(variant); db.flush()

        used_in_variant: set[str] = set()
        chosen_ids: list[str] = []
        for slot in assessment.blueprint:
            key = (slot["domain"], slot["difficulty"])
            pool = slot_pools[key]
            base = _deterministic_index(secret, f"{assessment.id}:{slot['position']}", len(pool))
            start_at = (base + variant_number) % len(pool)
            picked = next((pool[(start_at + offset) % len(pool)] for offset in range(len(pool)) if pool[(start_at + offset) % len(pool)].id not in used_in_variant), None)
            if picked is None:
                raise HTTPException(503, f"Insufficient distinct questions inside a variant for {key[0]} / {key[1]}")

            used_in_variant.add(picked.id)
            chosen_ids.append(picked.id)
            db.add(AssessmentVariantQuestion(variant_id=variant.id, question_id=picked.id, position=slot["position"]))

        signature = hashlib.sha256("|".join(chosen_ids).encode()).hexdigest()
        if signature in signatures and assessment.variant_count > 1:
            record_variant_collision()
        signatures.add(signature)

    db.flush()

def _variant_for_user(assessment: Assessment, user_id: int) -> int:
    secret = settings.assignment_secret or settings.jwt_secret
    return _deterministic_index(secret, f"{assessment.id}:{user_id}", max(1, assessment.variant_count))


def _variant_questions(db: Session, assessment_id: str, variant_number: int) -> list[Question]:
    variant = db.scalar(select(AssessmentVariant).where(
        AssessmentVariant.assessment_id == assessment_id,
        AssessmentVariant.variant_number == variant_number,
    ))
    if not variant:
        raise HTTPException(503, "Assessment variants are not prepared")

    pairs = db.execute(
        select(AssessmentVariantQuestion, Question)
        .join(Question, Question.id == AssessmentVariantQuestion.question_id)
        .where(AssessmentVariantQuestion.variant_id == variant.id)
        .order_by(AssessmentVariantQuestion.position)
    ).all()
    return [q for _, q in pairs]


def _make_presentation_seed(assessment_id: str, user_id: int) -> str:
    secret = settings.assignment_secret or settings.jwt_secret
    return hmac.new(
        secret.encode(), f"presentation:{assessment_id}:{user_id}".encode(), hashlib.sha256
    ).hexdigest()


def _seeded_index(seed: str, value: str, modulo: int) -> int:
    digest = hmac.new(seed.encode(), value.encode(), hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big") % modulo


def _candidate_presentation(seed: str, rows: list[Question]):
    """Reconstruct candidate order/options from one stored 64-char presentation seed.

    No per-question candidate assignment rows are required for new sessions. This
    keeps candidate-start writes O(1) while presentation remains deterministic.
    """
    order_seed = _seeded_index(seed, "question-order", 2**31 - 1)
    ordered = list(rows)
    random.Random(order_seed).shuffle(ordered)

    presented = []
    for position, q in enumerate(ordered, start=1):
        canonical_keys = list(q.options.keys())
        option_seed = _seeded_index(seed, f"options:{q.id}", 2**31 - 1)
        random.Random(option_seed).shuffle(canonical_keys)
        display_keys = [chr(ord("A") + i) for i in range(len(canonical_keys))]
        option_map = {display: canonical for display, canonical in zip(display_keys, canonical_keys)}
        public_options = {display: q.options[canonical] for display, canonical in option_map.items()}
        presented.append((position, q, option_map, public_options))
    return presented


def _claim_assessment_session(
    db: Session, assessment: Assessment, user: User, variant_number: int, total: int, started_at: datetime
):
    session_id = str(uuid.uuid4())
    session = AssessmentSession(
        id=session_id,
        assessment_id=assessment.id,
        user_id=user.id,
        status="active",
        started_at=started_at,
        deadline_at=started_at + timedelta(minutes=assessment.duration_minutes),
        total=total,
        variant_number=variant_number,
        presentation_seed=_make_presentation_seed(assessment.id, user.id),
    )
    db.add(session)
    try:
        # One candidate-start write regardless of paper size. Presentation is
        # reconstructed from variant_number + presentation_seed when needed.
        db.commit()
        db.refresh(session)
        return session
    except IntegrityError:
        db.rollback()
        # Same user may have clicked Start concurrently; the unique
        # assessment/user constraint elects one durable session.
        existing = db.scalar(select(AssessmentSession).where(
            AssessmentSession.assessment_id == assessment.id,
            AssessmentSession.user_id == user.id,
        ))
        if existing:
            return existing
        raise HTTPException(409, "Assessment session collision. Please retry.")


def _legacy_presentation(db: Session, session_id: str):
    """Read old persisted presentation rows so pre-migration attempts remain reviewable."""
    assignments = list(db.scalars(
        select(AssessmentQuestionAssignment)
        .where(AssessmentQuestionAssignment.session_id == session_id)
        .order_by(AssessmentQuestionAssignment.position)
    ).all())
    if not assignments:
        return []
    qids = [a.question_id for a in assignments]
    qmap = {q.id: q for q in db.scalars(select(Question).where(Question.id.in_(qids))).all()}
    presented = []
    for a in assignments:
        q = qmap.get(a.question_id)
        if not q:
            continue
        option_map = a.option_map or {k: k for k in q.options.keys()}
        public_options = {display: q.options[canonical] for display, canonical in option_map.items() if canonical in q.options}
        presented.append((a.position, q, option_map, public_options))
    return presented


def _presentation_for_session(db: Session, assessment: Assessment, session: AssessmentSession):
    # Existing deployments may have formal sessions created before the O(1)
    # presentation-seed migration. Preserve those exact persisted mappings.
    if not session.presentation_seed:
        legacy = _legacy_presentation(db, session.id)
        if legacy:
            return legacy

    variant_number = session.variant_number
    if variant_number is None:
        variant_number = _variant_for_user(assessment, session.user_id)
    rows = _variant_questions(db, assessment.id, variant_number)
    seed = session.presentation_seed or _make_presentation_seed(assessment.id, session.user_id)
    return _candidate_presentation(seed, rows)


def _public_for_session(db: Session, assessment: Assessment, session: AssessmentSession):
    out = []
    for _, q, _, public_options in _presentation_for_session(db, assessment, session):
        out.append(QuestionPublic(
            id=q.id, domain=q.domain, difficulty=q.difficulty, story_text=q.story_text, options=public_options
        ).model_dump())
    return out


def _candidate_insights(details: list[dict], score: int, total: int):
    def summarize(key: str):
        buckets: dict[str, dict[str, int]] = {}
        for row in details:
            label = str(row.get(key) or "Unknown")
            b = buckets.setdefault(label, {"correct": 0, "total": 0})
            b["total"] += 1
            b["correct"] += int(bool(row.get("correct")))
        result = []
        for label, b in buckets.items():
            accuracy = round(100 * b["correct"] / b["total"], 1) if b["total"] else 0
            result.append({"name": label, **b, "accuracy": accuracy})
        return sorted(result, key=lambda x: (x["accuracy"], -x["total"], x["name"]))

    by_domain = summarize("domain")
    by_difficulty = summarize("difficulty")
    weak = [x for x in by_domain if x["accuracy"] < 70][:3]
    strong = [x for x in reversed(by_domain) if x["accuracy"] >= 80][:3]
    recommendations = [f"Prioritize {x['name']} ({x['accuracy']}% in this assessment)." for x in weak]
    if not recommendations:
        recommendations = ["No major weak topic was detected in this attempt; review the questions you missed and increase difficulty gradually."]
    return {
        "score_percent": round(100 * score / total, 1) if total else 0,
        "by_domain": by_domain,
        "by_difficulty": by_difficulty,
        "weak_topics": weak,
        "strong_topics": strong,
        "recommendations": recommendations,
        "note": "These insights describe this assessment attempt only; they are not a psychometric skill estimate.",
    }


@router.get("/assessment/options")
def assessment_options(user: User = Depends(current_user)):
    return {
        "domains": all_domains(),
        "categories": domain_categories(),
        "difficulty_by_domain": domain_difficulty_map(),
        "generation": {
            "gemini_role": "neutral context prefix only; canonical stem is immutable",
            "answer_authority": "deterministic formula engine or curated CS fact bank",
            "candidate_path": "pre-generated variant lookup only",
        },
    }


def _validated_blueprint_input(body: AssessmentCreate):
    domains = list(dict.fromkeys(body.domains))
    unknown = [d for d in domains if d not in all_domains()]
    if unknown:
        raise HTTPException(400, f"Unknown concepts: {', '.join(unknown)}")
    total = body.easy_count + body.medium_count + body.hard_count
    if total <= 0:
        raise HTTPException(400, "Assessment must contain at least one question")
    if total > 100:
        raise HTTPException(400, "Assessment cannot contain more than 100 questions")
    capabilities = domain_difficulty_map()
    for difficulty, count in (("easy", body.easy_count), ("medium", body.medium_count), ("hard", body.hard_count)):
        if count and not any(difficulty in capabilities.get(domain, []) for domain in domains):
            raise HTTPException(400, f"None of the selected concepts can generate {difficulty} questions")
    seed = _blueprint_seed(body.title, domains, body.easy_count, body.medium_count, body.hard_count)
    blueprint = _build_blueprint(domains, body.easy_count, body.medium_count, body.hard_count, seed)
    if len(blueprint) != total:
        raise HTTPException(400, "Selected concepts cannot satisfy the requested difficulty distribution")
    return domains, total, blueprint


@router.post("/admin/assessments/preview")
def preview_assessment(body: AssessmentCreate, admin: User = Depends(admin_user)):
    domains, _, blueprint = _validated_blueprint_input(body)
    totals = {d: {"easy": 0, "medium": 0, "hard": 0, "total": 0} for d in domains}
    for slot in blueprint:
        totals[slot["domain"]][slot["difficulty"]] += 1
        totals[slot["domain"]]["total"] += 1
    variants = _variant_count(body.expected_candidates, body.candidates_per_variant)
    return {
        "blueprint": blueprint,
        "by_domain": totals,
        "total_questions": len(blueprint),
        "variant_count": variants,
        "expected_candidates": body.expected_candidates,
        "candidates_per_variant": body.candidates_per_variant,
    }


@router.post("/admin/assessments", response_model=AssessmentPublic)
def create_assessment(body: AssessmentCreate, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    domains, total, blueprint = _validated_blueprint_input(body)

    row = Assessment(
        id=str(uuid.uuid4()), title=body.title.strip(), duration_minutes=body.duration_minutes,
        easy_count=body.easy_count, medium_count=body.medium_count, hard_count=body.hard_count,
        domains=domains, blueprint=blueprint,
        expected_candidates=body.expected_candidates,
        candidates_per_variant=body.candidates_per_variant,
        variant_count=_variant_count(body.expected_candidates, body.candidates_per_variant),
        status="draft", created_by=admin.id,
    )
    db.add(row); db.commit(); db.refresh(row)
    return _assessment_public(row)


@router.get("/admin/assessments")
def list_assessments(db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    rows = list(db.scalars(select(Assessment).order_by(Assessment.created_at.desc()).limit(100)).all())
    return {"assessments": [_assessment_public(row) for row in rows]}


@router.post("/admin/assessments/{assessment_id}/activate", response_model=AssessmentPublic)
def activate_assessment(assessment_id: str, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    from sqlalchemy import text
    db.execute(text("SELECT pg_advisory_xact_lock(728419004)"))
    row = db.scalar(select(Assessment).where(Assessment.id == assessment_id).with_for_update())
    if not row:
        raise HTTPException(404, "Assessment not found")
    if row.status != "draft":
        raise HTTPException(409, "Only draft assessments can be activated; create a new assessment instead of reusing a closed one")

    # Prepare reusable variants before exposing the assessment to candidates.
    _prepare_variants(db, row)

    now = datetime.utcnow()
    db.execute(
        update(Assessment)
        .where(Assessment.status == "active", Assessment.id != row.id)
        .values(status="closed", closed_at=now)
    )
    db.flush()
    row.status = "active"; row.activated_at = now; row.closed_at = None
    try:
        db.commit(); db.refresh(row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Another assessment was activated concurrently. Retry the activation.")

    return _assessment_public(row)


@router.post("/admin/assessments/{assessment_id}/close", response_model=AssessmentPublic)
def close_assessment(assessment_id: str, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    row = db.get(Assessment, assessment_id)
    if not row:
        raise HTTPException(404, "Assessment not found")
    row.status = "closed"; row.closed_at = datetime.utcnow(); db.commit(); db.refresh(row)
    return _assessment_public(row)


@router.get("/assessments/active")
def active_assessment(db: Session = Depends(get_db), user: User = Depends(current_user)):
    # Preserve resumability for a candidate who already started, even if an
    # admin has since closed the assessment to new candidates.
    pair = db.execute(
        select(AssessmentSession, Assessment)
        .join(Assessment, Assessment.id == AssessmentSession.assessment_id)
        .where(AssessmentSession.user_id == user.id, AssessmentSession.status.in_(["active", "expired"]))
        .order_by(AssessmentSession.started_at.desc())
        .limit(1)
    ).first()
    if pair:
        return {"assessment": _assessment_public(pair[1]), "candidate_status": "active" if datetime.utcnow() <= pair[0].deadline_at else "expired", "review_available": False}

    row = db.scalar(select(Assessment).where(Assessment.status == "active").order_by(Assessment.activated_at.desc()))
    if row:
        existing = db.scalar(select(AssessmentSession).where(AssessmentSession.assessment_id == row.id, AssessmentSession.user_id == user.id))
        candidate_status = existing.status if existing else "not_started"
        if existing and existing.status == "active" and datetime.utcnow() > existing.deadline_at + timedelta(seconds=10):
            candidate_status = "expired"
        return {
            "assessment": _assessment_public(row),
            "candidate_status": candidate_status,
            "review_available": bool(existing and existing.status == "submitted" and _review_available(db, row)),
        }

    # No globally active assessment: surface the candidate's latest submitted
    # assessment so a post-close review remains discoverable in the UI.
    past = db.execute(
        select(AssessmentSession, Assessment)
        .join(Assessment, Assessment.id == AssessmentSession.assessment_id)
        .where(AssessmentSession.user_id == user.id, AssessmentSession.status == "submitted")
        .order_by(AssessmentSession.submitted_at.desc())
        .limit(1)
    ).first()
    if past:
        return {
            "assessment": _assessment_public(past[1]),
            "candidate_status": "submitted",
            "review_available": _review_available(db, past[1]),
        }
    return {"assessment": None}


@router.post("/assessments/{assessment_id}/start", response_model=AssessmentStartResponse)
def start_admin_assessment(assessment_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(404, "Assessment not found")

    if not rate_limit(f"assessment-start:user-{user.id}", settings.start_rate_limit_per_minute):
        raise HTTPException(429, "Too many assessment start/resume requests")

    existing = db.scalar(select(AssessmentSession).where(
        AssessmentSession.assessment_id == assessment.id, AssessmentSession.user_id == user.id
    ))
    if existing:
        if existing.status not in {"active", "expired"}:
            raise HTTPException(409, "You have already submitted this assessment")
        remaining = max(0, int((existing.deadline_at - datetime.utcnow()).total_seconds()))
        return {
            "session_id": existing.id, "assessment": _assessment_public(assessment),
            "started_at": existing.started_at.isoformat() + "Z", "deadline_at": existing.deadline_at.isoformat() + "Z",
            "answers": existing.answers, "current_index": existing.current_index, "revision": existing.revision,
            "duration_seconds": remaining, "questions": _public_for_session(db, assessment, existing),
        }

    if assessment.status != "active":
        raise HTTPException(409, "This assessment is closed to new candidates")

    variant_number = _variant_for_user(assessment, user.id)
    rows = _variant_questions(db, assessment.id, variant_number)
    expected_total = assessment.easy_count + assessment.medium_count + assessment.hard_count
    if len(rows) != expected_total:
        raise HTTPException(503, "Selected assessment variant is incomplete")

    started_at = datetime.utcnow()
    session = _claim_assessment_session(
        db, assessment, user, variant_number, len(rows), started_at
    )
    record_quiz_started()
    remaining = max(0, int((session.deadline_at - datetime.utcnow()).total_seconds()))

    return {
        "session_id": session.id, "assessment": _assessment_public(assessment),
        "started_at": session.started_at.isoformat() + "Z", "deadline_at": session.deadline_at.isoformat() + "Z",
        "answers": session.answers, "current_index": session.current_index, "revision": session.revision,
        "duration_seconds": remaining,
        "questions": _public_for_session(db, assessment, session),
    }

def _review_available(db: Session, assessment: Assessment) -> bool:
    if settings.reveal_results_while_active:
        return True
    if assessment.status == "active":
        return False
    live = db.scalar(
        select(func.count()).select_from(AssessmentSession).where(
            AssessmentSession.assessment_id == assessment.id,
            AssessmentSession.status == "active",
            AssessmentSession.deadline_at > datetime.utcnow(),
        )
    ) or 0
    return live == 0


@router.post("/assessments/{assessment_id}/submit", response_model=QuizResult)
def submit_admin_assessment(assessment_id: str, body: AssessmentSubmit, db: Session = Depends(get_db), user: User = Depends(current_user)):
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(404, "Assessment not found")

    # Row locking makes a double-click / concurrent submit idempotent at the
    # state-transition boundary: only one request can move active -> submitted.
    session = db.scalar(select(AssessmentSession).where(
        AssessmentSession.id == body.session_id,
        AssessmentSession.assessment_id == assessment_id,
        AssessmentSession.user_id == user.id,
    ).with_for_update())
    if not session:
        raise HTTPException(404, "Assessment session not found")
    if session.status == "submitted":
        if not _review_available(db, assessment):
            return QuizResult(score=None, total=session.total, results=[], review_available=False)
        return my_assessment_review(assessment_id, db, user)
    if session.status not in {"active", "expired"}:
        raise HTTPException(409, "This assessment is no longer active")

    now = datetime.utcnow()

    presented = _presentation_for_session(db, assessment, session)
    assigned_ids = [q.id for _, q, _, _ in presented]
    expired = now > session.deadline_at
    submitted_ids = list((session.answers or {}).keys()) if expired else [a.question_id for a in body.answers]
    if len(submitted_ids) != len(set(submitted_ids)):
        raise HTTPException(400, "Duplicate question IDs in submission")
    assigned_set = set(assigned_ids)
    if any(qid not in assigned_set for qid in submitted_ids):
        raise HTTPException(400, "Submission contains a question that was not assigned")

    selected = dict(session.answers or {}) if expired else {a.question_id: a.selected_option.upper() for a in body.answers}
    results = []
    details = []
    score = 0
    for _, q, option_map, _ in presented:
        display_option = selected.get(q.id, "")
        if display_option and display_option not in option_map:
            raise HTTPException(400, f"Invalid option for question {q.id}")
        canonical_option = option_map.get(display_option, "")
        ok = bool(canonical_option) and canonical_option == q.correct_option.upper()
        score += int(ok)
        inverse = {canonical: display for display, canonical in option_map.items()}
        results.append(AnswerResult(
            question_id=q.id,
            selected_option=display_option or "-",
            correct_option=inverse.get(q.correct_option.upper(), q.correct_option.upper()),
            correct=ok,
            solution=q.canonical_solution,
        ))
        details.append({"question_id": q.id, "domain": q.domain, "difficulty": q.difficulty, "correct": ok})

    actual_duration = max(
        0,
        min(
            int((now - session.started_at).total_seconds()),
            int((session.deadline_at - session.started_at).total_seconds()),
        ),
    )
    session.status = "submitted"
    session.submitted_at = now
    session.score = score
    session.duration_seconds = actual_duration
    session.answers = selected
    session.details = details
    db.commit()

    total = len(presented)
    insights = _candidate_insights(details, score, total)
    if not _review_available(db, assessment):
        return QuizResult(score=None, total=total, results=[], insights=None, review_available=False)
    return QuizResult(score=score, total=total, results=results, insights=insights, review_available=True)


@router.get("/assessments/{assessment_id}/insights/me")
def my_assessment_insights(assessment_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(404, "Assessment not found")
    if not _review_available(db, assessment):
        raise HTTPException(409, "Review is available after the assessment closes and active sessions finish")
    session = db.scalar(select(AssessmentSession).where(
        AssessmentSession.assessment_id == assessment_id,
        AssessmentSession.user_id == user.id,
        AssessmentSession.status == "submitted",
    ))
    if not session:
        raise HTTPException(404, "No submitted attempt found")
    return _candidate_insights(session.details or [], session.score or 0, session.total)


@router.get("/assessments/{assessment_id}/review/me", response_model=QuizResult)
def my_assessment_review(assessment_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(404, "Assessment not found")
    if not _review_available(db, assessment):
        raise HTTPException(409, "Review is available after the assessment closes and active sessions finish")

    session = db.scalar(select(AssessmentSession).where(
        AssessmentSession.assessment_id == assessment_id,
        AssessmentSession.user_id == user.id,
        AssessmentSession.status == "submitted",
    ))
    if not session:
        raise HTTPException(404, "No submitted attempt found")

    selected = session.answers or {}
    results = []
    for _, q, option_map, _ in _presentation_for_session(db, assessment, session):
        display_option = str(selected.get(q.id, "") or "").upper()
        canonical_option = option_map.get(display_option, "")
        inverse = {canonical: display for display, canonical in option_map.items()}
        results.append(AnswerResult(
            question_id=q.id,
            selected_option=display_option or "-",
            correct_option=inverse.get(q.correct_option.upper(), q.correct_option.upper()),
            correct=bool(canonical_option) and canonical_option == q.correct_option.upper(),
            solution=q.canonical_solution,
        ))

    insights = _candidate_insights(session.details or [], session.score or 0, session.total)
    return QuizResult(
        score=session.score or 0, total=session.total, results=results,
        insights=insights, review_available=True,
    )


@router.get("/admin/assessments/{assessment_id}/leaderboard")
def assessment_leaderboard(
    assessment_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin: User = Depends(admin_user),
):
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(404, "Assessment not found")

    base = (
        select(AssessmentSession, User).join(User, User.id == AssessmentSession.user_id)
        .where(AssessmentSession.assessment_id == assessment_id, AssessmentSession.status == "submitted")
        .order_by(AssessmentSession.score.desc(), AssessmentSession.duration_seconds.asc(), AssessmentSession.submitted_at.asc())
    )
    rows = db.execute(base.offset(offset).limit(limit)).all()
    total = db.scalar(
        select(func.count()).select_from(AssessmentSession).where(
            AssessmentSession.assessment_id == assessment_id, AssessmentSession.status == "submitted"
        )
    ) or 0
    leaderboard = [{
        "rank": offset + rank, "user_id": candidate.id, "name": candidate.name,
        "score": session.score or 0, "total": session.total,
        "duration_seconds": session.duration_seconds or 0,
        "submitted_at": session.submitted_at.isoformat() + "Z" if session.submitted_at else "",
        "variant_number": session.variant_number,
    } for rank, (session, candidate) in enumerate(rows, start=1)]
    return {
        "assessment": _assessment_public(assessment),
        "leaderboard": leaderboard,
        "pagination": {"offset": offset, "limit": limit, "total": total},
    }



@router.post("/assessment-sessions/{session_id}/draft")
def save_assessment_draft(session_id: str, body: SessionDraft,
                          db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = db.scalar(select(AssessmentSession).where(AssessmentSession.id == session_id,
        AssessmentSession.user_id == user.id).execution_options(populate_existing=True).with_for_update())
    if not session:
        raise HTTPException(404, "Assessment session not found")
    if session.status != "active" or datetime.utcnow() > session.deadline_at:
        raise HTTPException(409, "Time has ended. Submit the answers already saved on the server.")
    if session.revision != body.revision:
        raise HTTPException(409, "Another tab changed this assessment. Reload to restore saved answers.")
    assessment = db.get(Assessment, session.assessment_id)
    presented = _presentation_for_session(db, assessment, session)
    options = {q.id: option_map for _, q, option_map, _ in presented}
    if set(body.answers) - set(options) or body.current_index >= len(options):
        raise HTTPException(400, "Draft does not match this assessment")
    if any(choice not in options[qid] for qid, choice in body.answers.items()):
        raise HTTPException(400, "Invalid displayed option")
    session.answers, session.current_index = body.answers, body.current_index
    session.revision += 1
    db.commit()
    return {"revision": session.revision}
