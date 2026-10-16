from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import sessionmaker

from app.models import GenerationJob, Question, User
from app.core.config import settings
from app.services.generation_batches import create_batch, dispatch_pending, claim_job, finish_job, retry_job, batch_progress
from app.services.generation import generate_one_ai_question, _question_fingerprint

pytestmark = pytest.mark.integration
DOMAIN = "Time, Speed & Distance"


def test_logical_identity_ignores_names_context_and_cs_wording():
    from core.model_registry import generate_model_question
    from core.cs_question_engine import build_cs_question, FACTS
    q = generate_model_question("Time, Speed & Distance", "easy")
    original = _question_fingerprint(q)
    q["variables"]["vehicle_type"] = "a different name"
    q["story_text"] = "a different presentation"
    assert _question_fingerprint(q) == original
    domain = next(iter(FACTS))
    cs = build_cs_question(domain, "ALL")
    identity = _question_fingerprint(cs)
    cs["story_text"] = "a different question pattern"
    assert _question_fingerprint(cs) == identity


def make_batch(db, count=12):
    return create_batch(db, 1, DOMAIN, "easy", count)


def test_full_request_is_persisted_beyond_concurrency_cap(db, monkeypatch):
    monkeypatch.setattr(settings, "generation_max_pending_per_bucket", 5)
    batch = make_batch(db)
    messages = []
    assert dispatch_pending(db, lambda *args: messages.append(args)) == 5
    progress = batch_progress(db, batch)
    assert progress["requested"] == 12
    assert progress["queued"] == 5
    assert progress["pending"] == 7
    assert dispatch_pending(db, lambda *args: messages.append(args)) == 0


def test_broker_failure_retains_all_requested_work(db):
    batch = make_batch(db, 7)
    def broken(*args):
        raise ConnectionError("offline")
    assert dispatch_pending(db, broken) == 0
    progress = batch_progress(db, batch)
    assert progress["pending"] == 7
    assert progress["queued"] == 0
    assert db.scalar(select(func.count()).select_from(GenerationJob)) == 7
    messages = []
    dispatch_pending(db, lambda *args: messages.append(args), datetime.utcnow() + timedelta(minutes=1))
    assert len(messages) == min(7, settings.generation_max_pending_per_bucket)


def test_expired_reservation_rejects_old_dispatch_token(db):
    batch = make_batch(db, 1)
    old = []
    dispatch_pending(db, lambda *args: old.append(args))
    newer = []
    future = datetime.utcnow() + timedelta(seconds=settings.generation_lease_seconds + 1)
    dispatch_pending(db, lambda *args: newer.append(args), future)
    assert old[0][1] != newer[0][1]
    assert claim_job(db, *old[0]) is None
    assert claim_job(db, *newer[0]) is not None


def test_redelivery_does_not_run_a_job_twice(db):
    make_batch(db, 1)
    messages = []
    dispatch_pending(db, lambda *args: messages.append(args))
    assert claim_job(db, *messages[0]) is not None
    assert claim_job(db, *messages[0]) is None
    assert finish_job(db, *messages[0], {"generated": 0, "reason": "duplicate"})
    assert claim_job(db, *messages[0]) is None


def test_completed_and_rejected_outcomes_are_distinct(db):
    batch = make_batch(db, 2)
    messages = []
    dispatch_pending(db, lambda *args: messages.append(args))
    claim_job(db, *messages[0])
    result = generate_one_ai_question(db, DOMAIN, "easy", commit=False)
    assert result["generated"] == 1
    assert finish_job(db, *messages[0], result)
    claim_job(db, *messages[1])
    finish_job(db, *messages[1], {"generated": 0, "reason": "duplicate"})
    progress = batch_progress(db, batch)
    assert progress["succeeded"] == 1
    assert progress["rejected"] == 1
    assert progress["status"] == "completed_with_issues"
    assert progress["reasons"] == {"duplicate": 1}


def test_question_and_job_outcome_commit_atomically(db):
    make_batch(db, 1)
    messages = []
    dispatch_pending(db, lambda *args: messages.append(args))
    claim_job(db, *messages[0])
    result = generate_one_ai_question(db, DOMAIN, "easy", commit=False)
    with sessionmaker(db.bind)() as observer:
        assert observer.get(Question, result["question_id"]) is None
    assert finish_job(db, *messages[0], result)
    with sessionmaker(db.bind)() as observer:
        assert observer.get(Question, result["question_id"]) is not None
        assert observer.get(GenerationJob, messages[0][0]).status == "succeeded"


def test_superseded_worker_cannot_publish_question(db):
    make_batch(db, 1)
    messages = []
    dispatch_pending(db, lambda *args: messages.append(args))
    claim_job(db, *messages[0])
    # Another dispatcher supersedes a stalled worker before its final write.
    with sessionmaker(db.bind)() as other:
        job = other.get(GenerationJob, messages[0][0])
        job.status = "queued"
        job.dispatch_token = "replacement"
        other.commit()
    result = generate_one_ai_question(db, DOMAIN, "easy", commit=False)
    assert not finish_job(db, *messages[0], result)
    assert db.get(Question, result["question_id"]) is None


def test_attempt_limit_records_failure(db):
    batch = make_batch(db, 1)
    for _ in range(settings.generation_max_job_attempts):
        messages = []
        dispatch_pending(db, lambda *args: messages.append(args), datetime.utcnow() + timedelta(hours=1))
        assert claim_job(db, *messages[0])
        retry_job(db, *messages[0])
    assert batch_progress(db, batch)["failed"] == 1


def test_parallel_dispatchers_share_bucket_cap(db, monkeypatch):
    monkeypatch.setattr(settings, "generation_max_pending_per_bucket", 5)
    make_batch(db, 25)
    factory = sessionmaker(db.bind, expire_on_commit=False)
    def dispatch(_):
        with factory() as session:
            return dispatch_pending(session, lambda *args: None)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(dispatch, range(4))) == 5
    assert db.scalar(select(func.count()).select_from(GenerationJob).where(GenerationJob.status == "queued")) == 5


def test_batch_api_persists_work_even_when_broker_is_down(db, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.db import get_db
    from app.core.auth import admin_user
    def session_override():
        yield db
    app.dependency_overrides[get_db] = session_override
    app.dependency_overrides[admin_user] = lambda: db.get(User, 1)
    def unavailable():
        raise ConnectionError("offline")
    monkeypatch.setattr("app.workers.tasks.dispatch_generation_jobs.delay", unavailable)
    try:
        client = TestClient(app)
        response = client.post("/api/admin/question-factory/generate", json={"domain": DOMAIN, "difficulty": "easy", "count": 100})
        assert response.status_code == 202
        payload = response.json()
        assert payload["batch"]["pending"] == 100
        assert payload["worker_notified"] is False
        detail = client.get(f"/api/admin/question-factory/batches/{payload['batch']['id']}")
        assert detail.json()["requested"] == 100
        assert len(client.get("/api/admin/question-factory/batches").json()["batches"]) == 1
        assert client.post("/api/admin/question-factory/generate", json={"domain": DOMAIN, "difficulty": "easy", "count": 101}).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_migration_is_repeatable(db):
    sql = (Path(__file__).resolve().parents[1] / "MIGRATION_GENERATION_BATCHES.sql").read_text()
    for _ in range(2):
        with db.bind.connect() as connection:
            connection.exec_driver_sql(sql)
            connection.commit()
