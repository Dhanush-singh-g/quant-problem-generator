"""Workers execute durable jobs; Beat recovers pending and interrupted batches."""
import logging

from .celery_app import celery
from ..core.db import SessionLocal
from ..services.generation import generate_one_ai_question
from ..services.generation_batches import dispatch_pending, claim_job, finish_job, retry_job

logger = logging.getLogger(__name__)


def _publish(job_id, token):
    process_generation_job.apply_async(args=[job_id, token], queue="generation")


@celery.task(name="app.workers.tasks.dispatch_generation_jobs", ignore_result=True)
def dispatch_generation_jobs():
    with SessionLocal() as db:
        return {"published": dispatch_pending(db, _publish)}


@celery.task(name="app.workers.tasks.process_generation_job", ignore_result=True,
             soft_time_limit=90, time_limit=120)
def process_generation_job(job_id, token):
    with SessionLocal() as db:
        job = claim_job(db, job_id, token)
        if job is None:
            return {"ignored": True}
        domain, difficulty = job.domain, job.difficulty
        try:
            result = generate_one_ai_question(db, domain, difficulty, commit=False)
            # Lock again so a lease recovery cannot race with publication.
            if not finish_job(db, job_id, token, result):
                return {"ignored": True}
        except Exception:
            db.rollback()
            logger.warning("Generation job failed; retry recorded: %s", job_id)
            retry_job(db, job_id, token)
            result = {"generated": 0, "reason": "generation_error"}
    try:
        # Promptly fill the next slots; Beat remains the durable recovery path.
        dispatch_generation_jobs.delay()
    except Exception:
        logger.warning("Generation wakeup unavailable; Beat will recover pending work")
    return result
