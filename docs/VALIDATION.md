# Validation record

The packaged local application was validated in the cloud workspace on
16 October 2026. These results concern this source and local test infrastructure,
not the user's laptop, hosted database or external integration accounts.

## Passed

- **79 automated tests**: all 21 quantitative models (2,100 sampled questions),
  curated CS buckets, answer/unit/story/solution tampering, legacy password
  compatibility and Argon2id, authentication/logout/roles/CSRF, practice
  ownership/resume/draft conflicts/concurrent starts, saved solution gating,
  correct/incorrect/skipped analytics, server duration, idempotent submission,
  timed assessment expiry/review/leaderboard, inventory audit, first-response
  statistics, durable generation recovery, parallel dispatchers, atomic
  publication, and fresh/repeatable migrations.
- Both original offline validation scripts passed. The original deterministic
  script exercised 450 samples across its 18 original models.
- Frontend production build and TypeScript checks passed on native Node and in
  the Node 22 standalone Docker build.
- Runtime Python and full frontend dependency audits reported **zero known
  advisories** at validation time. Python runtime dependencies use a universal,
  hash-verified lock; frontend uses `npm ci` and its lockfile.
- **Two complete browser scenarios passed against the packaged production Docker
  server**: registration, immediate navigation update, practice answer/position
  recovery after refresh, durable result review, profile, bookmark removal,
  mobile navigation, revision mode, discard, logout, admin batch processing,
  assessment creation/activation, candidate resume, delayed review and leaderboard.
- PostgreSQL, Redis, API, worker, Beat and web all passed container health checks.
  Migrations exited successfully before API/worker startup.
- Initial offline seed added **216** approved starter questions; immediately
  rerunning it added **zero** and preserved data.
- Complete `docker compose down` / `up --no-build --wait` recreation preserved
  user, question, attempt and generation-job counts in named volumes.
- A short burst of **100 authenticated requests at 20 concurrent requests** returned
  100 successful responses with the correct account role. This is a smoke check,
  not a capacity benchmark for thousands of candidates.
- PowerShell 7 on Linux parsed the setup script, generated configuration without
  printing secrets, and preserved that configuration on repeat runs.

The cloud's Docker build needed its existing proxy DNS and CA supplied through
build-only configuration. TLS and package-hash checks remained enabled. That
workspace-specific override is not part of the laptop configuration. Native and
Docker application services were actually started; the browser checks were not
replaced with static source checks.

## Reproduce safely

Integration tests **clear tables** in the explicitly configured PostgreSQL test
database. Use a disposable database whose name ends in `_test`. Do not use your
working account/database or a database used by running workers.

From the project root with the Python virtual environment activated:

```powershell
python -m pip install -r backend/requirements-dev.txt
$env:QUANTFORGE_TEST_DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:5432/quantforge_test"
$env:DATABASE_URL = $env:QUANTFORGE_TEST_DATABASE_URL
$env:REDIS_URL = "redis://HOST:6379/0"
python -m pytest -q
python scripts/validate_final_pass.py
$env:PYTHONPATH = "."
python scripts/validate_question_factory_quality.py
```

Without the explicit test-database variable, database tests skip. The pure model
and password tests still execute. Python 3.12 emits some deprecation warnings for
legacy UTC-naive timestamp helpers; they do not represent test failures.

For browser tests, start a disposable complete stack and seed its inventory.
These tests create users, questions and assessments, so do not point them at a
working production instance. From `frontend/`:

```powershell
npm ci
npx playwright install chromium
$env:E2E_BASE_URL = "http://localhost:3000"
$env:E2E_ADMIN_EMAIL = "YOUR_DISPOSABLE_ADMIN_EMAIL"
# Set E2E_ADMIN_PASSWORD privately in your terminal; never send it in chat.
npm run test:e2e
```

The admin scenario skips when credentials are omitted. Both scenarios ran during
validation. On hosts with an already installed supported Chromium binary,
`CHROME_EXECUTABLE_PATH` can select it. `npm run build` validates frontend types
and production output. `npm audit` and `pip-audit -r backend/requirements.txt`
repeat the dependency advisory checks.

## Boundaries

Docker Desktop/WSL 2, Windows PowerShell 5.1 and this user's laptop have not been
executed here. The setup initializer was exercised with PowerShell on Linux and
the exact Compose/Docker application workflow ran on Linux. Optional Google and
Gemini were not called with live user credentials. Supported models are finite;
observed difficulty needs real responses and is explicitly provisional. No
claim of exhaustive bug absence or public-production certification is made.
