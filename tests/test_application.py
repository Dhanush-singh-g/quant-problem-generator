from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from app.core.auth import create_token, hash_password, verify_password
from app.core.config import settings
from app.core.db import get_db
from app.main import app
from app.models import Question, QuizSession, QuizAttempt, UserQuestionHistory, User, AssessmentSession
from app.services.generation import generate_questions
from app.audit_inventory import audit

pytestmark = pytest.mark.integration
DOMAIN = "Time, Speed & Distance"


@pytest.fixture
def client(db, monkeypatch):
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr("app.api.routes.rate_limit", lambda *a, **k: True)
    monkeypatch.setattr("app.api.practice.rate_limit", lambda *a, **k: True)
    c = TestClient(app, headers={"Origin": "http://localhost:3000"})
    c.cookies.set(settings.auth_cookie_name, create_token(db.get(User, 1)))
    try:
        yield c
    finally:
        app.dependency_overrides.clear()


def seed(db, count=15):
    result = generate_questions(db, count, DOMAIN, False, "medium")
    assert result["generated"] >= 5


def start(client, count=5, mode="unseen"):
    r = client.post("/api/practice/sessions", json={"count": count, "domain": DOMAIN, "difficulty": "medium", "mode": mode})
    assert r.status_code == 201, r.text
    return r.json()


def test_registration_login_logout_and_role_protection(db, client):
    client.cookies.clear()
    r = client.post("/api/auth/register", json={"name": "  ", "email": "candidate@example.com", "password": "Strong-pass-123"})
    assert r.status_code == 422
    r = client.post("/api/auth/register", json={"name": "Candidate", "email": "candidate@example.com", "password": "Strong-pass-123"})
    assert r.status_code == 200, r.text
    assert "httponly" in r.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").json()["name"] == "Candidate"
    assert client.get("/api/admin/metrics").status_code == 403
    token = client.cookies.get(settings.auth_cookie_name)
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "candidate@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "candidate@example.com", "password": "Strong-pass-123"}).status_code == 200


def test_cookie_csrf_and_native_bearer(db, client):
    token = create_token(db.get(User, 1))
    assert client.post("/api/auth/logout", headers={"Origin": "https://attacker.invalid"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"Authorization": "Bearer " + token, "Origin": "https://attacker.invalid"}).status_code == 200


def test_practice_resume_drafts_and_tab_conflict(db, client):
    seed(db)
    session = start(client)
    qid = session["questions"][0]["id"]
    assert "correct_option" not in session["questions"][0]
    r = client.post(f"/api/practice/sessions/{session['session_id']}/draft", json={"answers": {qid: "B"}, "current_index": 2, "revision": 0})
    assert r.json()["revision"] == 1
    resumed = client.get("/api/practice/active").json()["session"]
    assert resumed["answers"] == {qid: "B"} and resumed["current_index"] == 2
    assert start(client)["session_id"] == session["session_id"]
    assert client.post(f"/api/practice/sessions/{session['session_id']}/draft", json={"answers": {}, "current_index": 0, "revision": 0}).status_code == 409
    assert client.get(f"/api/practice/sessions/{session['session_id']}").json()["answers"] == {qid: "B"}


def test_server_scoring_analytics_idempotency_and_solution_gating(db, client):
    seed(db)
    session = start(client)
    questions = session["questions"]
    qid = questions[0]["id"]
    assert client.post(f"/api/practice/questions/{qid}/save", json={"saved": True}).status_code == 200
    saved = client.get("/api/practice/saved").json()["questions"][0]
    assert saved["solution"] is None and saved["correct_option"] is None
    stored = db.get(QuizSession, session["session_id"])
    stored.created_at = datetime.utcnow() - timedelta(seconds=30)
    db.commit()
    answers = [{"question_id": q["id"], "selected_option": db.get(Question, q["id"]).correct_option} for q in questions[:2]]
    payload = {"session_id": session["session_id"], "answers": answers, "duration_seconds": 999999}
    r = client.post("/api/quiz/submit", json=payload)
    assert r.status_code == 200 and r.json()["score"] == 2
    assert client.post("/api/quiz/submit", json=payload).json() == r.json()
    assert db.scalar(select(func.count()).select_from(QuizAttempt)) == 1
    assert 30 <= db.scalar(select(QuizAttempt)).duration_seconds < 60
    stats = client.get("/api/analytics/me").json()
    assert stats["profile"]["name"] == "Test Admin"
    assert stats["correct_answers"] == 2 and stats["incorrect_answers"] == 0
    assert stats["skipped_answers"] == 3 and stats["questions_answered"] == 2
    assert stats["questions_completed"] == 5 and stats["accuracy"] == 40
    assert client.get("/api/practice/saved").json()["questions"][0]["review_available"]
    assert client.get(f"/api/practice/sessions/{session['session_id']}").json()["result"]["score"] == 2
    available = client.get("/api/practice/inventory").json()
    assert sum(row["count"] for row in available["revision"]) == 5
    new = start(client)
    assert not set(q["id"] for q in new["questions"]) & set(q["id"] for q in questions)


def test_abandon_releases_uncompleted_inventory_and_revision_is_explicit(db, client):
    seed(db)
    session = start(client)
    available = client.get("/api/practice/inventory").json()
    assert sum(row["count"] for row in available["revision"]) == 0
    assert client.post(f"/api/practice/sessions/{session['session_id']}/abandon").status_code == 200
    assert client.get("/api/practice/active").json()["session"] is None
    assert client.get("/api/practice/inventory").json() == available
    assert client.post("/api/practice/sessions", json={"count": 1, "mode": "revision"}).status_code == 409


def test_ownership_and_invalid_answers(db, client):
    seed(db)
    session = start(client)
    assert client.post("/api/quiz/submit", json={"session_id": session["session_id"], "answers": [{"question_id": "foreign", "selected_option": "A"}]}).status_code == 400
    other = User(name="Other", email="other@example.com", password_hash="unused")
    db.add(other); db.commit()
    client.cookies.clear(); client.cookies.set(settings.auth_cookie_name, create_token(other))
    assert client.get(f"/api/practice/sessions/{session['session_id']}").status_code == 404
    assert client.post(f"/api/practice/sessions/{session['session_id']}/abandon").status_code == 404
    assert client.post("/api/quiz/submit", json={"session_id": session["session_id"], "answers": []}).status_code == 404


def test_concurrent_starts_share_one_practice_session(db, client):
    from sqlalchemy.orm import sessionmaker
    from app.api.practice import start as start_session
    from app.schemas import PracticeStart
    from app.models import QuestionAssignment
    seed(db)
    factory = sessionmaker(db.bind, expire_on_commit=False)
    def request(_):
        with factory() as session:
            return start_session(PracticeStart(count=5, domain=DOMAIN, difficulty="medium"), session, session.get(User, 1))["session_id"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(request, range(4)))
    assert len(set(ids)) == 1
    assert db.scalar(select(func.count()).select_from(QuizSession)) == 1
    assert db.scalar(select(func.count()).select_from(QuestionAssignment)) == 5


def test_existing_inventory_audit_quarantines_and_preserves_history(db, client):
    seed(db)
    q = db.scalar(select(Question))
    q.answer_unit = "bananas"; db.commit()
    report = audit(db)
    assert report["quarantined"] == 1 and q.active
    report = audit(db, apply=True)
    assert report["quarantined"] == 1
    db.refresh(q)
    assert not q.active and q.review_status == "quarantined"
    assert db.get(Question, q.id) is not None


def test_timed_assessment_draft_expiry_and_leaderboard(db, client, monkeypatch):
    seed(db, 20)
    monkeypatch.setattr(settings, "reveal_results_while_active", False)
    body = {"title": "Test paper", "duration_minutes": 1, "easy_count": 0, "medium_count": 2, "hard_count": 0,
            "domains": [DOMAIN], "expected_candidates": 10, "candidates_per_variant": 5}
    assert client.post("/api/admin/assessments/preview", json=body).json()["total_questions"] == 2
    paper = client.post("/api/admin/assessments", json=body).json()
    assert client.post(f"/api/admin/assessments/{paper['id']}/activate").status_code == 200
    session = client.post(f"/api/assessments/{paper['id']}/start").json()
    qid = session["questions"][0]["id"]
    saved = {qid: "B"}
    assert client.post(f"/api/assessment-sessions/{session['session_id']}/draft", json={"answers": saved, "current_index": 1, "revision": 0}).status_code == 200
    resumed = client.post(f"/api/assessments/{paper['id']}/start").json()
    assert resumed["answers"] == saved and resumed["current_index"] == 1
    stored = db.get(AssessmentSession, session["session_id"])
    stored.started_at = datetime.utcnow() - timedelta(minutes=2)
    stored.deadline_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    # A late request cannot replace saved answers, even by sending a different option.
    result = client.post(f"/api/assessments/{paper['id']}/submit", json={"session_id": session["session_id"], "answers": [{"question_id": qid, "selected_option": "A"}]}).json()
    assert result["review_available"] is False
    db.refresh(stored)
    assert stored.answers == saved and stored.duration_seconds == 60
    assert client.post(f"/api/admin/assessments/{paper['id']}/close").status_code == 200
    review = client.get(f"/api/assessments/{paper['id']}/review/me").json()
    assert review["review_available"] and review["results"][0]["selected_option"] == "B"
    leaderboard = client.get(f"/api/admin/assessments/{paper['id']}/leaderboard").json()
    assert leaderboard["pagination"]["total"] == 1


def test_observed_difficulty_uses_first_unseen_responses_only(db, client):
    seed(db)
    q = db.scalar(select(Question))
    for n in range(30):
        user = User(name=f"Response {n}", email=f"response-{n}@example.com", password_hash="unused")
        db.add(user); db.flush()
        correct = n < 15
        first = {"question_id": q.id, "domain": q.domain, "difficulty": q.difficulty,
                 "correct": correct, "answered": True, "mode": "unseen"}
        db.add(QuizAttempt(user_id=user.id, score=int(correct), total=1,
                          answers={q.id: "A"}, details=[first], duration_seconds=10))
        db.add(QuizAttempt(user_id=user.id, score=1, total=1,
                          answers={q.id: "A"}, details=[{**first, "correct": True, "mode": "revision"}], duration_seconds=5))
    db.commit()
    response = client.get("/api/admin/question-factory/calibration?limit=200")
    assert response.status_code == 200, response.text
    measured = next(item for item in response.json()["items"] if item["question_id"] == q.id)
    assert measured["first_exposures"] == 30 and measured["accuracy"] == 50
    assert measured["observed_band"] == "medium" and q.difficulty == measured["curated_difficulty"]
