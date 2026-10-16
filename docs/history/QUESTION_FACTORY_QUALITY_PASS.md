# QuantForge Question Factory — Quality Pass

This iteration keeps assessment delivery independent from generation and improves the asynchronous AI Question Factory rather than adding candidate-history features.

## Pipeline

`Pool Manager -> Redis/Celery -> Gemini proposal -> schema/math guard -> structural diversity gate -> dual deterministic solvers -> deterministic difficulty gate -> plausible distractor gate -> PostgreSQL validated pool`

Rejected proposals are never stored in the candidate-visible pool. A generation job may request another proposal sequentially after a quality rejection; the shared Redis/Gemini limiter still enforces the aggregate API request ceiling.

## Structural diversity

Each AI quantitative question gets a structural descriptor built from the arithmetic AST shape, variable count, structure name and subdomain. The new question is compared with recent validated questions in the same topic/difficulty bucket. Highly similar structures are rejected even if names, numbers or story wording differ.

## Difficulty

Difficulty is no longer accepted because Gemini labels a question easy/medium/hard. The backend calculates a deterministic score from operation count, variable count, reasoning-step count, expression nesting, division count and exponent use. The computed band must match the requested bucket.

## Distractors

Distractors are not random +/- percentages by default. The backend mutates arithmetic operators in the proposed expression to model common mistakes, evaluates those mutations safely, removes impossible/extreme/duplicate values, then uses bounded common-error fallbacks only if needed. All four options remain server-owned.

## Queue backpressure

Redis maintains a short-lived pending counter per topic/difficulty bucket. Celery Beat and manual replenishment can reserve only up to `GENERATION_MAX_PENDING_PER_BUCKET` jobs for that bucket. This stops repeated pool audits from stacking the same deficit while earlier jobs are still queued or running.

## Observability

Redis now tracks Question Factory requested, accepted, rejected, duplicate, verification-failed, difficulty-mismatch, diversity-rejected, distractor-failed, proposal-invalid, AI-unavailable, queue-deduped counts, rejection reasons, average generation latency and acceptance rate. They are exposed under `question_factory` in `/admin/metrics`.

## New settings

- `GENERATION_QUALITY_ATTEMPTS=3`
- `GENERATION_MAX_PENDING_PER_BUCKET=5`
- `GENERATION_RETRY_BACKOFF_SECONDS=20` (reserved for future delayed retry scheduling)

## Validation performed

- Offline easy/medium/hard quality-gate validation passed.
- Structural duplicate rejection and novel-structure acceptance passed.
- Plausible distractor validation passed.
- AI proposal integration was tested with mocked Gemini JSON for easy, medium and hard questions.
- `python -m compileall -q backend agents core services utils scripts` passed.

No candidate-history / never-repeat table is included in this iteration; that remains intentionally deferred to the next version.

## Difficulty reassignment update

A target-band miss is no longer automatically a rejection. The prompt still asks Gemini for a band, but the deterministic classifier owns the final label. A verified question requested as Hard but measured as Medium is stored in the Medium pool when its logical content hash is not already present. This preserves useful generation work without weakening mathematical verification.
