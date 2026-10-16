"""Durable batch orchestration. Redis carries notifications, PostgreSQL owns work."""
from datetime import datetime, timedelta
import logging
import uuid

from sqlalchemy import select, func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..models import GenerationBatch, GenerationBucket, GenerationJob
from ..core.config import settings

logger = logging.getLogger(__name__)
ACTIVE = ("queued", "running")
TERMINAL = ("succeeded", "rejected", "failed")


def create_batch(db, user_id, domain, difficulty, count):
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    db.execute(insert(GenerationBucket).values(domain=domain, difficulty=difficulty).on_conflict_do_nothing())
    batch = GenerationBatch(id=str(uuid.uuid4()), requested_by=user_id, domain=domain,
                            difficulty=difficulty, requested_count=count)
    db.add(batch)
    db.flush()
    db.add_all([GenerationJob(id=str(uuid.uuid4()), batch_id=batch.id, domain=domain,
                              difficulty=difficulty) for _ in range(count)])
    db.commit()
    return batch


def batch_progress(db, batch):
    counts = dict(db.execute(select(GenerationJob.status, func.count())
                            .where(GenerationJob.batch_id == batch.id)
                            .group_by(GenerationJob.status)).all())
    counts = {status: int(counts.get(status, 0)) for status in (*ACTIVE, "pending", *TERMINAL)}
    completed = sum(counts[s] for s in TERMINAL)
    reasons = dict(db.execute(select(GenerationJob.error_code, func.count())
                             .where(GenerationJob.batch_id == batch.id,
                                    GenerationJob.error_code.is_not(None), GenerationJob.status.in_(TERMINAL))
                             .group_by(GenerationJob.error_code)).all())
    status = "pending" if completed == 0 and counts["pending"] == batch.requested_count else "processing"
    if completed == batch.requested_count:
        status = "completed" if counts["succeeded"] == batch.requested_count else "completed_with_issues"
    return {"id": batch.id, "domain": batch.domain, "difficulty": batch.difficulty,
            "requested": batch.requested_count, **counts, "completed": completed,
            "status": status, "reasons": reasons, "created_at": batch.created_at.isoformat() + "Z"}


def dispatch_pending(db, publish, now=None):
    """Reserve slots with row locks, then publish. Expired leases recover lost work.

    A publish failure returns only the unpublished job to pending. A unique token
    prevents an old/redelivered message from claiming a newer reservation.
    """
    now = now or datetime.utcnow()
    buckets = db.execute(select(GenerationJob.domain, GenerationJob.difficulty)
                         .where(GenerationJob.status.in_(("pending", *ACTIVE)))
                         .distinct()).all()
    published = 0
    for domain, difficulty in buckets:
        bucket = db.scalar(select(GenerationBucket).where(
            GenerationBucket.domain == domain, GenerationBucket.difficulty == difficulty
        ).with_for_update(skip_locked=True))
        if bucket is None:
            db.rollback()
            continue
        expired = db.scalars(select(GenerationJob).where(
            GenerationJob.domain == domain, GenerationJob.difficulty == difficulty,
            GenerationJob.status.in_(ACTIVE), GenerationJob.lease_until <= now,
        ).with_for_update(skip_locked=True)).all()
        for job in expired:
            job.status = "failed" if job.attempts >= settings.generation_max_job_attempts else "pending"
            job.error_code = "worker_lease_expired"
            job.available_at = now
            job.lease_until = None
            job.dispatch_token = None
        db.flush()
        active = db.scalar(select(func.count()).select_from(GenerationJob).where(
            GenerationJob.domain == domain, GenerationJob.difficulty == difficulty,
            GenerationJob.status.in_(ACTIVE),
        )) or 0
        room = max(0, settings.generation_max_pending_per_bucket - active)
        jobs = list(db.scalars(select(GenerationJob).where(
            GenerationJob.domain == domain, GenerationJob.difficulty == difficulty,
            GenerationJob.status == "pending", GenerationJob.available_at <= now,
        ).order_by(GenerationJob.created_at, GenerationJob.id).limit(room)
            .with_for_update(skip_locked=True)).all())
        reservations = []
        for job in jobs:
            job.status = "queued"
            job.dispatch_token = str(uuid.uuid4())
            job.lease_until = now + timedelta(seconds=settings.generation_lease_seconds)
            reservations.append((job.id, job.dispatch_token))
        db.commit()
        for job_id, token in reservations:
            try:
                publish(job_id, token)
                published += 1
            except Exception:
                logger.warning("Generation dispatch unavailable; job retained: %s", job_id)
                db.execute(update(GenerationJob).where(
                    GenerationJob.id == job_id, GenerationJob.status == "queued",
                    GenerationJob.dispatch_token == token,
                ).values(status="pending", dispatch_token=None, lease_until=None,
                         available_at=now + timedelta(seconds=settings.generation_retry_backoff_seconds),
                         error_code="broker_unavailable"))
                db.commit()
    return published


def claim_job(db, job_id, token):
    job = db.scalar(select(GenerationJob).where(GenerationJob.id == job_id)
                    .execution_options(populate_existing=True).with_for_update())
    if not job or job.status != "queued" or job.dispatch_token != token:
        db.rollback()
        return None
    job.status = "running"
    job.attempts += 1
    job.lease_until = datetime.utcnow() + timedelta(seconds=settings.generation_lease_seconds)
    job.error_code = None
    db.commit()
    return job


def finish_job(db, job_id, token, result):
    job = db.scalar(select(GenerationJob).where(GenerationJob.id == job_id)
                    .execution_options(populate_existing=True).with_for_update())
    if not job or job.status != "running" or job.dispatch_token != token:
        # Discard any question from a worker whose lease was superseded.
        db.rollback()
        return False
    job.status = "succeeded" if result.get("generated") else "rejected"
    job.question_id = result.get("question_id")
    job.error_code = None if job.status == "succeeded" else str(result.get("reason", "quality_rejected"))[:80]
    job.lease_until = None
    # This commits the newly generated question and its outcome together.
    db.commit()
    return True


def retry_job(db, job_id, token):
    job = db.scalar(select(GenerationJob).where(GenerationJob.id == job_id)
                    .execution_options(populate_existing=True).with_for_update())
    if not job or job.status != "running" or job.dispatch_token != token:
        db.rollback()
        return
    job.status = "failed" if job.attempts >= settings.generation_max_job_attempts else "pending"
    job.available_at = datetime.utcnow() + timedelta(seconds=settings.generation_retry_backoff_seconds * job.attempts)
    job.error_code = "generation_error"
    job.dispatch_token = None
    job.lease_until = None
    db.commit()
