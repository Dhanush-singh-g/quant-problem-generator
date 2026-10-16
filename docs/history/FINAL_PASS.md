# QuantForge AI — Final Engineering Pass

This pass closes the main correctness, security and scalability gaps found while running the project locally.

## Correctness

- Quantitative Easy/Medium/Hard is implemented by different mathematical structures, not post-generation labels.
- Solver A uses `core/formula_engine.py`; Solver B uses the separately implemented `core/verification_engine.py`.
- The validator requires both solvers, the generator answer and the canonical MCQ option to agree.
- CS questions are checked against the curated fact bank.
- New questions use a logical SHA-256 `content_hash`; PostgreSQL enforces uniqueness.
- Gemini cannot replace the canonical stem. It can only add a neutral context prefix that passes semantic/leakage guards.

## Scalable assessment delivery

- Formal assessments use a bounded number of reusable variants.
- HMAC-SHA256 maps a candidate to a variant without predictable `user_id % N` behavior.
- Every variant uses the same stored topic/difficulty blueprint.
- Candidate question and option order are reconstructed from a stored `presentation_seed`.
- New candidate starts write one session row regardless of paper size; no per-question candidate-assignment inserts are required.
- Legacy persisted assignment rows remain readable after migration.
- Candidate start contains no Gemini call, question generation or Celery dependency.

## Security

- JWT is delivered only as an HttpOnly cookie.
- Production uses `__Host-` cookie naming, `Secure`, explicit HTTPS CORS origins and an Origin-based CSRF guard.
- JWTs carry issuer/audience/iat/exp claims; authorization role is re-read from PostgreSQL.
- Password hashing uses `bcrypt_sha256` for new passwords while continuing to verify legacy bcrypt hashes.
- Authentication is limited by both IP and hashed account identity through Redis.
- Google ID credentials are verified by FastAPI against the configured Google client ID.
- Production can withhold score, solutions and insights until an assessment is closed and live sessions finish.
- Production API docs/OpenAPI are disabled.
- Input collection sizes/IDs are bounded.
- Concurrent formal submissions lock the session row before the active -> submitted transition.

## Distributed infrastructure

- Redis: Celery broker, shared AI cache, distributed rate limits, AI request coordination and metrics.
- Celery: late acknowledgements, retry/backoff, low prefetch, worker recycling.
- PostgreSQL: durable source of truth with candidate/leaderboard/pool indexes and integrity constraints.
- `/api/health/live` and `/api/health/ready` support orchestrators/load balancers.

## Candidate feedback

Once review is permitted, the API returns accuracy by topic and difficulty plus prioritized review suggestions. These describe the current attempt only and do not claim psychometric skill estimation.

## Migration order

For an old database:

1. `MIGRATION_HARDENING.sql`
2. `MIGRATION_VARIANTS.sql`
3. `MIGRATION_FINAL_PASS.sql`

If the first two were already run, run only `MIGRATION_FINAL_PASS.sql` now.

## Production environment baseline

```env
ENVIRONMENT=production
COOKIE_SECURE=true
RATE_LIMIT_FAIL_OPEN=false
AUTO_CREATE_SCHEMA=false
REVEAL_RESULTS_WHILE_ACTIVE=false
BOOTSTRAP_ADMIN=false
JWT_SECRET=<32+ random characters>
ASSIGNMENT_SECRET=<different 32+ random characters>
CORS_ORIGINS=https://your-frontend.example
```

Keep `COOKIE_SAMESITE=lax` when frontend/API are same-site. Use `none` only for a genuinely cross-site HTTPS deployment.

## Validation scope

Backend compilation and deterministic offline validation cover all 18 quantitative templates. A stress pass generated and validated 3,600 quantitative samples. This is application validation, not a substitute for real concurrent load testing or psychometric calibration.
