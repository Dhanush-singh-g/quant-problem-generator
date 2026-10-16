"""Resumable practice, explicit revision, and server-authoritative results."""
from datetime import datetime, timezone
import random
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..core.auth import current_user
from ..core.db import get_db
from ..core.config import settings
from ..models import Question, User, UserQuestionHistory, QuizSession, QuestionAssignment, QuizAttempt
from ..schemas import PracticeStart, SessionDraft, SubmitQuiz, SaveQuestionRequest
from ..services.generation import all_domains, VALID_DIFFICULTIES
from ..services.cache import rate_limit

router = APIRouter(prefix="/api")


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc(value):
    return value.isoformat() + "Z"


def enabled():
    if not settings.enable_practice_mode:
        raise HTTPException(404, "Practice mode is disabled")


def session_rows(db, session):
    return list(db.scalars(select(Question).join(QuestionAssignment, QuestionAssignment.question_id == Question.id)
                           .where(QuestionAssignment.session_id == session.id).order_by(QuestionAssignment.position)).all())


def public_question(q):
    return {key: getattr(q, key) for key in ("id", "domain", "difficulty", "story_text", "options")}


def payload(db, session):
    return {"session_id": session.id, "status": session.status, "domain": session.domain,
            "difficulty": session.difficulty, "mode": session.mode, "questions": [public_question(q) for q in session_rows(db, session)],
            "answers": session.answers or {}, "current_index": session.current_index, "revision": session.revision,
            "started_at": utc(session.created_at), "server_time": utc(now()), "result": session.result or None,
            "source": "postgres-practice-pool"}


def owned(db, session_id, user, lock=False):
    stmt = select(QuizSession).where(QuizSession.id == session_id, QuizSession.user_id == user.id)
    if lock:
        stmt = stmt.execution_options(populate_existing=True).with_for_update()
    session = db.scalar(stmt)
    if not session:
        raise HTTPException(404, "Practice session not found")
    return session


def inventory_query(user, mode):
    completed = select(UserQuestionHistory.question_id).where(
        UserQuestionHistory.user_id == user.id, UserQuestionHistory.completed_count > 0)
    query = select(Question).where(Question.active.is_(True), Question.review_status == "approved")
    return query.where(Question.id.in_(completed) if mode == "revision" else Question.id.not_in(completed))


@router.get("/practice/inventory")
def inventory(db: Session = Depends(get_db), user: User = Depends(current_user)):
    enabled()
    result = {}
    for mode in ("unseen", "revision"):
        subquery = inventory_query(user, mode).subquery()
        rows = db.execute(select(subquery.c.domain, subquery.c.difficulty, func.count())
                          .group_by(subquery.c.domain, subquery.c.difficulty)).all()
        result[mode] = [{"domain": d, "difficulty": b, "count": n} for d, b, n in rows]
    return result


@router.get("/practice/active")
def active(db: Session = Depends(get_db), user: User = Depends(current_user)):
    enabled()
    session = db.scalar(select(QuizSession).where(QuizSession.user_id == user.id, QuizSession.status == "active"))
    return {"session": payload(db, session) if session else None}


@router.get("/practice/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    enabled()
    return payload(db, owned(db, session_id, user))


@router.post("/practice/sessions", status_code=201)
def start(body: PracticeStart, db: Session = Depends(get_db), user: User = Depends(current_user)):
    enabled()
    if not rate_limit(f"practice-start:{user.id}", settings.start_rate_limit_per_minute):
        raise HTTPException(429, "Too many practice start requests. Try again shortly.")
    if body.domain != "ALL" and body.domain not in all_domains():
        raise HTTPException(400, "Unknown topic")
    if body.difficulty not in VALID_DIFFICULTIES:
        raise HTTPException(400, "Unknown difficulty")
    # Serialize starts per account so two tabs cannot consume different sets.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    existing = db.scalar(select(QuizSession).where(QuizSession.user_id == user.id, QuizSession.status == "active"))
    if existing:
        return payload(db, existing)
    query = inventory_query(user, body.mode)
    if body.domain != "ALL":
        query = query.where(Question.domain == body.domain)
    if body.difficulty != "ALL":
        query = query.where(Question.difficulty == body.difficulty)
    rows = list(db.scalars(query.order_by(Question.created_at.desc()).limit(500)).all())
    random.shuffle(rows)
    if len(rows) < body.count:
        raise HTTPException(409, {"message": "Choose a smaller set or another topic/mode; an administrator can add inventory.",
                                  "available": len(rows), "requested": body.count})
    rows = rows[:body.count]
    session = QuizSession(id=str(uuid.uuid4()), user_id=user.id, domain=body.domain,
                          difficulty=body.difficulty, question_count=len(rows), status="active", mode=body.mode)
    db.add(session)
    db.flush()
    for position, q in enumerate(rows):
        db.add(QuestionAssignment(session_id=session.id, question_id=q.id, position=position + 1))
        history = db.scalar(select(UserQuestionHistory).where(UserQuestionHistory.user_id == user.id,
                                                              UserQuestionHistory.question_id == q.id))
        if history:
            history.seen_count += 1
            history.last_seen_at = now()
        else:
            db.add(UserQuestionHistory(user_id=user.id, question_id=q.id))
    db.commit()
    return payload(db, session)


@router.post("/practice/sessions/{session_id}/draft")
def save_draft(session_id: str, body: SessionDraft, db: Session = Depends(get_db), user: User = Depends(current_user)):
    enabled()
    session = owned(db, session_id, user, True)
    if session.status != "active":
        raise HTTPException(409, "This set is no longer active")
    if session.revision != body.revision:
        raise HTTPException(409, "Another tab updated this set. Reload to recover the latest saved answers.")
    ids = {q.id for q in session_rows(db, session)}
    if set(body.answers) - ids or body.current_index >= len(ids):
        raise HTTPException(400, "Draft does not match this set")
    session.answers = body.answers
    session.current_index = body.current_index
    session.revision += 1
    db.commit()
    return {"revision": session.revision}


@router.post("/practice/sessions/{session_id}/abandon")
def abandon(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    enabled()
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    session = owned(db, session_id, user, True)
    if session.status == "active":
        session.status = "abandoned"
        db.commit()
    return {"ok": True}


@router.post("/quiz/submit")
def submit(body: SubmitQuiz, db: Session = Depends(get_db), user: User = Depends(current_user)):
    enabled()
    session = owned(db, body.session_id, user, True)
    if session.status == "submitted" and session.result:
        return session.result
    if session.status != "active":
        raise HTTPException(409, "This set is no longer active")
    rows = session_rows(db, session)
    selected = {item.question_id: item.selected_option.upper() for item in body.answers}
    if len(selected) != len(body.answers) or set(selected) - {q.id for q in rows}:
        raise HTTPException(400, "Answers must refer to distinct questions assigned to this set")
    score, results, details = 0, [], []
    for q in rows:
        choice = selected.get(q.id, "")
        correct = bool(choice) and choice == q.correct_option
        score += int(correct)
        results.append({"question_id": q.id, "selected_option": choice, "correct_option": q.correct_option,
                        "correct": correct, "solution": q.canonical_solution})
        details.append({"question_id": q.id, "domain": q.domain, "difficulty": q.difficulty,
                        "correct": correct, "answered": bool(choice), "mode": session.mode})
        history = db.scalar(select(UserQuestionHistory).where(UserQuestionHistory.user_id == user.id,
                                                              UserQuestionHistory.question_id == q.id).with_for_update())
        if history is None:
            history = UserQuestionHistory(user_id=user.id, question_id=q.id, completed_count=0,
                attempt_count=0, correct_count=0, incorrect_count=0)
            db.add(history)
        history.completed_count += 1
        history.attempt_count += int(bool(choice))
        history.correct_count += int(correct)
        history.incorrect_count += int(bool(choice) and not correct)
        history.last_correct = correct if choice else None
        history.last_seen_at = now()
    result = {"score": score, "total": len(rows), "results": results, "review_available": True}
    db.add(QuizAttempt(user_id=user.id, score=score, total=len(rows), answers=selected, details=details,
                       duration_seconds=max(0, int((now() - session.created_at).total_seconds()))))
    session.status, session.submitted_at, session.answers, session.result = "submitted", now(), selected, result
    db.commit()
    return result


@router.post("/practice/questions/{question_id}/save")
def save(question_id: str, body: SaveQuestionRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    history = db.scalar(select(UserQuestionHistory).where(UserQuestionHistory.user_id == user.id,
                                                          UserQuestionHistory.question_id == question_id).with_for_update())
    if not history:
        raise HTTPException(404, "Question is not in your practice history")
    history.saved, history.saved_at = body.saved, now() if body.saved else None
    db.commit()
    return {"question_id": question_id, "saved": history.saved}


@router.get("/practice/saved")
def saved(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
          db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(UserQuestionHistory, Question).join(Question, Question.id == UserQuestionHistory.question_id).where(
        UserQuestionHistory.user_id == user.id, UserQuestionHistory.saved.is_(True))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.execute(query.order_by(UserQuestionHistory.saved_at.desc(), Question.id).offset(offset).limit(limit)).all()
    return {"total": total, "questions": [dict(public_question(q),
        solution=q.canonical_solution if h.completed_count else None,
        correct_option=q.correct_option if h.completed_count else None,
        review_available=bool(h.completed_count), saved_at=utc(h.saved_at) if h.saved_at else None,
        attempt_count=h.attempt_count, last_correct=h.last_correct) for h, q in rows]}


@router.get("/analytics/me")
def analytics(db: Session = Depends(get_db), user: User = Depends(current_user)):
    attempts = list(db.scalars(select(QuizAttempt).where(QuizAttempt.user_id == user.id).order_by(QuizAttempt.created_at.desc())).all())
    total, correct, answered = sum(a.total for a in attempts), sum(a.score for a in attempts), 0
    domains, bands = {}, {}
    for attempt in attempts:
        for detail in attempt.details or []:
            answered += int(detail.get("answered", detail["question_id"] in (attempt.answers or {})))
            for bucket, key in ((domains, detail.get("domain", "Unknown")), (bands, detail.get("difficulty", "unknown"))):
                row = bucket.setdefault(key, {"correct": 0, "total": 0})
                row["total"] += 1
                row["correct"] += int(bool(detail.get("correct")))
    for bucket in (domains, bands):
        for row in bucket.values():
            row["accuracy"] = round(100 * row["correct"] / row["total"], 1)
            row["strength"] = ("building_data" if row["total"] < 5 else "strong" if row["accuracy"] >= 75
                               else "needs_practice" if row["accuracy"] < 50 else "developing")
    return {"profile": {"name": user.name}, "attempts": len(attempts), "questions_answered": answered,
            "questions_completed": total, "correct_answers": correct, "incorrect_answers": answered - correct,
            "skipped_answers": total - answered, "accuracy": round(100 * correct / total, 1) if total else 0,
            "avg_seconds_per_question": round(sum(a.duration_seconds for a in attempts) / total, 1) if total else 0,
            "by_domain": domains, "by_difficulty": bands,
            "recent": [{"id": a.id, "score": a.score, "total": a.total, "created_at": utc(a.created_at)} for a in attempts[:8]]}
