# Manual Question Factory + Practice Profile Pass

## Product decision
Question generation is administrator-controlled. Candidate practice requests never invoke Gemini, never enqueue generation jobs, and never trigger automatic replenishment.

## Manual factory
The admin dashboard exposes topic, difficulty and count controls. Submitting a batch queues one-question Celery jobs through Redis. Existing queue backpressure and Gemini rate limiting still apply. The dashboard shows validated inventory by topic/difficulty plus accepted, rejected, reassigned, duplicate and verification metrics.

There is deliberately no Celery Beat schedule. Run only the generation worker when the administrator wants the factory to process queued work:

`celery -A app.workers.celery_app:celery worker --loglevel=info --pool=solo -Q generation`

The admin can stop the worker whenever generation should stop. Existing queued jobs remain in Redis until a worker consumes them.

## Practice behavior
Users explicitly choose the topic and difficulty they want. QuantForge does not automatically redirect them toward weak topics. If the selected unseen inventory is insufficient, practice returns an inventory-shortage response and does not start generation.

## Profile analytics
The existing practice attempt data now produces topic and difficulty strength labels. Labels require at least five answered questions: >=75% is Strong, <50% is Needs practice, otherwise Developing. Smaller samples are Building data. These labels are descriptive only; the user remains in control of practice selection.
