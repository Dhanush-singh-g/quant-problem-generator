# Generation update

## Implemented

- Imported the uploaded source into the existing repository.
- Made a reviewed mathematical model registry the factory correctness boundary.
- Registered the 18 existing models and added three multi-stage Hard models:
  approaching vehicles with a pause, a joining worker, and a delayed tank outlet.
- Added independent conservation checks, model-specific distractors for the new
  models, parameter/unit checks, immutable canonical solutions, and option validation.
- Restricted optional AI to selecting reviewed neutral context. AI failure falls
  back to canonical wording; generation works without Gemini.
- Persisted every requested batch/job in PostgreSQL. The per-bucket limit now
  controls concurrency instead of dropping the rest of a request.
- Added lease recovery, stale-token protection, duplicate-message handling,
  broker-failure recovery, bounded attempts, and atomic question/job commits.
- Added batch creation/list/detail API endpoints and a polling progress dashboard
  with separate published, rejected, failed, queued, running and pending counts.
- Added a Celery Beat dispatcher and a repeatable PostgreSQL migration.
- Fixed a duplicate saved-history index name that broke fresh database creation.
- Restored the environment template and documented Windows/local setup, migration
  order, scheduler requirements, and the deployment limits.

## Verified in the local validation environment

- 64 automated tests passed, including 2,100 quantitative samples across all 21
  registered models, CS publication checks, tampering rejection, PostgreSQL
  concurrency/recovery tests and API batch persistence.
- Both pre-existing offline validation scripts passed. The original deterministic
  script generated 450 samples across its 18 original models.
- Frontend production build and TypeScript validation passed.
- Docker Compose configuration validated.
- A live local workflow authenticated through FastAPI, persisted a request for
  100 questions, processed it with real Redis/Celery/Beat, published 100 questions,
  then delivered and scored a five-question practice set.
- The new database migration was executed twice successfully.

## Applying the update

Keep your existing credentials outside this source bundle. Apply
`MIGRATION_GENERATION_BATCHES.sql` after missing earlier migrations, then restart
the API, worker and one Beat scheduler as documented in README.md. Stop old
workers first and resubmit any old untracked generation requests through the new
batch endpoint. This source bundle has not been deployed to your database.

Optional live Gemini was not tested; its failure/response handling was tested with
controlled responses. Existing inventory is preserved, not retroactively
validated or rehashed. Unsupported AI structures remain outside production
publication. Curated difficulty is not response-calibrated. Older imported
framework/auth dependencies need a security upgrade before public deployment.
Unrelated profile, login-navigation and practice-resume issues are outside this
generation change.
