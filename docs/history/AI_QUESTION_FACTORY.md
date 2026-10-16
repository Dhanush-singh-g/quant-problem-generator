# QuantForge AI Question Factory (Architecture B)

Question generation and assessment delivery are intentionally independent systems.

## Generation plane

`Celery Beat -> Pool Audit -> Redis Queue -> one-question Celery job -> Gemini -> deterministic verification -> PostgreSQL`

The pool audit runs every five minutes. It checks each topic/difficulty bucket and queues only the deficit. Each queued generation task creates **one** question and performs at most one Gemini generation request. On the Gemini free tier, run the generation queue with one worker process (`--concurrency=1` or Windows `--pool=solo`) and keep `AI_RPM` below the provider limit.

For quantitative aptitude, Gemini now proposes the actual problem structure in a constrained arithmetic DSL. It returns a story template, numeric variables, an answer expression, unit, reasoning steps and a structure name. The backend does not trust Gemini's answer. It parses the expression with a strict AST whitelist and evaluates it independently using a float evaluator and a Decimal evaluator. Only proposals where both evaluators agree, the story placeholders match the variables, the expression complexity fits the requested difficulty, and the payload passes bounds are accepted.

Gemini never executes code. Calls, attributes, indexing and arbitrary Python syntax are rejected. Candidate delivery never calls Gemini.

## Delivery plane

`Candidate -> FastAPI -> PostgreSQL validated pool/variants -> assessment`

If inventory is insufficient, the API queues replenishment and fails fast instead of synchronously generating questions. This prevents candidate traffic from consuming Gemini quota or increasing exam-start latency.

## Why this preserves quality and scalability

Scalability is achieved by decoupling production from consumption, not by reducing every topic to three fixed templates. The AI factory can accumulate diverse verified questions continuously while the assessment system serves only previously validated inventory. Candidate concurrency therefore scales with FastAPI/PostgreSQL/Redis capacity, while question-generation throughput scales independently with Gemini quota and Celery workers.

## Recommended free-tier processes

Backend:
`uvicorn app.main:app --reload`

Generation worker (Windows):
`celery -A app.workers.celery_app:celery worker --loglevel=info --pool=solo -Q generation`

Pool scheduler:
`celery -A app.workers.celery_app:celery beat --loglevel=info`

For production, run worker and beat as separate services and use a managed Redis instance.

## Quality-control iteration

The factory now adds deterministic structural-diversity, difficulty and distractor gates before a generated question can enter the validated pool. Redis also caps pending generation jobs per topic/difficulty bucket so repeated audits cannot create a queue burst. See `QUESTION_FACTORY_QUALITY_PASS.md` for the exact rules and validation performed.
