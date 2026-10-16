# Question generation architecture

The production factory uses reviewed mathematical models and curated CS facts.
FastAPI persists an entire admin-requested batch in PostgreSQL, Redis transports
notifications, and Celery workers publish validated questions. Practice reads the
question bank; it never triggers AI or generation.

## Correctness boundary

1. `core/model_registry.py` registers 18 existing quantitative models and three
   new multi-stage models. Each defines topic, difficulty, story, parameter
   ranges, increments, and units. Unsupported structures cannot be published.
2. Parameters are sampled within those ranges. The solver rejects impossible
   states before a question is returned.
3. `core/formula_engine.py` computes the answer and explanation. The new phase
   engine conserves distance/work/tank capacity across chronological intervals.
4. `core/verification_engine.py` independently recomputes the answer. Publication
   also requires matching units, four distinct options, the canonical story,
   parameter grid, and the exact model-rendered solution.
5. Distractors use model-specific common mistakes where available, with numeric
   fallbacks. They are not all misconception-calibrated.
6. Optional Gemini selects a context ID from reviewed neutral phrases. Arbitrary
   AI text, numbers, formulas, options and explanations are ignored. A timeout,
   malformed response, missing key or rate limit falls back to canonical wording.
7. A stable hash rejects exact logical duplicates. Quantitative names and AI
   context are excluded from identity; numerical values remain part of it.
   A CS fact has one identity even when presented with a different question pattern.
8. Newly generated questions and their successful job outcomes commit together.

The unrestricted AI proposal and semantic-verifier modules remain as historical
experimental code. No production factory route or worker calls them. Agreement
at a single numerical input is not used as the production correctness boundary.

## Durable batch processing

Every requested question gets a `generation_jobs` row. Requesting 100 questions
creates 100 rows; a concurrency limit of five leaves the remainder pending.
Statuses are `pending`, `queued`, `running`, `succeeded`, `rejected`, and `failed`.

The dispatcher takes a PostgreSQL row lock per topic/difficulty bucket before
reserving slots. This coordinates replicas without treating Redis counters as
work records. It publishes only after committing reservations. Failed publication
returns that job to pending with a delay; unconfirmed publication is recovered
when its lease expires. Tokens prevent old/redelivered messages from claiming
newer reservations. A stale worker's attempted question insertion is rolled back.

A completed job wakes the dispatcher. Celery Beat also dispatches every ten
seconds, recovering pending jobs and expired leases after interruptions. This
scheduler services existing admin batches; it does not automatically create new
inventory requests. Run one Beat instance, alongside at least one worker.

Unexpected generation failures retry up to `GENERATION_MAX_JOB_ATTEMPTS` with
backoff. Quality/duplicate exhaustion is a terminal rejection. Requested counts
are job counts, not a promise that every requested question will pass publication.
CS inventory is finite and can be exhausted; new curated facts must be added to
expand it. Batch progress comes from PostgreSQL, not best-effort Redis metrics.

## Deployment and migration

Use `python -m app.migrate` to apply versioned migrations, including
`MIGRATION_GENERATION_BATCHES.sql` and `MIGRATION_APPLICATION.sql`. It creates
only the three orchestration tables and their indexes. It is safe to rerun.
Existing question inventory is preserved with a pending review status. Run
`python -m app.audit_inventory` for a report and `--apply` in maintenance mode
to approve supported questions and quarantine invalid or duplicate inventory.
The audit also rebuilds logical identities from the older scheme, which included
textual parameters and CS wording. Referenced history is preserved.

Stop old workers before switching versions. Old untracked `generate_one_question`
messages use a retired task name and are not resumed; record any outstanding
old requests and submit them through the new batch API after upgrading.

Defaults:

- `GENERATION_MAX_PENDING_PER_BUCKET=5`: queued/running jobs per bucket.
- `GENERATION_QUALITY_ATTEMPTS=3`: candidate attempts before rejection.
- `GENERATION_MAX_JOB_ATTEMPTS=3`: attempts for unexpected execution failures.
- `GENERATION_RETRY_BACKOFF_SECONDS=20`: retry base delay.
- `GENERATION_LEASE_SECONDS=180`: lost reservation recovery interval.
- `GENERATION_USE_AI_CONTEXT=false`: generation works without Gemini.

Worker task limits are 90 seconds soft / 120 seconds hard where the worker pool
supports them. Optional AI has a 15-second request timeout. Keep leases longer
than task execution and the expected queue wait; tune the bucket cap to worker
capacity. Windows `solo` workers do not provide all prefork time-limit guarantees.

## Extension and limitations

Add new structures to the reviewed registry, implement canonical and independent
solvers, and add conservation/boundary tests before enabling them. The three new
Hard models cover a vehicle pause, a joining worker, and a delayed outlet. This
is a supported-model library, not arbitrary mathematical invention.

Difficulty is curated by structure, not calibrated by operation count or AI
labels. The dashboard reports provisional first-exposure accuracy when enough real
responses exist; it does not automatically change curated difficulty. Richer
reviewed models remain a future extension. This version does not claim
production-scale load testing.
