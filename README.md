# QuantForge

This complete local release supersedes the earlier generation-only package.
See [RELEASE_NOTES.md](RELEASE_NOTES.md) for the changes.

A local aptitude and computer-science practice application with server-saved
progress, revision bookmarks, performance profiles, timed assessments, and an
administrator Question Factory.

## Start on your Windows laptop

Install Docker Desktop with the WSL 2 backend and use Linux containers. Extract
this project into a normal folder, open PowerShell there, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

The script preserves an existing `.env`, otherwise creates independent random
application/database secrets and administrator credentials. It builds and checks
all services, applies versioned migrations, and adds an offline starter question
bank. No Gemini key, Supabase account, hosted Redis, Python or Node installation
is required for this Docker workflow.

Open **http://localhost:3000**. Read `ADMIN_EMAIL` and `ADMIN_PASSWORD` privately
from your local `.env` to sign in as administrator. Register a separate candidate
account to practise. Do not share `.env` or include it in ZIP files.

First-time image/package downloads can take several minutes. See
[WINDOWS_SETUP.md](WINDOWS_SETUP.md) for port changes, logs, native development,
existing-database upgrades, backup, and recovery instructions.

## What works

- Email/password sign-in with Argon2id, HttpOnly cookies and server-side roles.
  Existing bcrypt/bcrypt-sha256 passwords migrate on successful login. Logout
  invalidates all existing tokens for the account.
- Practice answers and question position save to PostgreSQL. Refresh/resume works
  across browser restarts. Conflicting tabs cannot silently overwrite drafts.
- New-question and revision modes are explicit. Availability is counted for the
  signed-in account. Abandoned, uncompleted questions remain available.
- Solutions stay hidden in saved questions until the set is completed. Completed
  sets have durable reviews and duplicate submissions do not create extra attempts.
- Profile accuracy, correct/wrong/skipped totals and topic summaries agree with
  completed attempts. Elapsed durations come from the server and include time
  spent away from a session.
- Admin-created timed assessments support distribution preview, reusable variants,
  server-saved answers, resume, delayed review and leaderboards. After expiry only
  answers saved before the server deadline are scored.
- All requested generation jobs persist. Five concurrent jobs does not discard
  the remainder of a larger batch. Retries, lease recovery and publication
  outcomes are visible in the dashboard.
- Only approved question inventory enters new practice sets or assessment variants.
  Existing questions can be audited without deleting historical attempts.

## Generation architecture

The production Question Factory uses 21 supported quantitative models, including
three multi-stage motion/work/tank models, and a curated CS fact bank. Canonical
and independent solvers validate mathematical answers and units. Model-specific
mistakes supply distractors where available. Optional AI selects neutral context
from reviewed phrases; it cannot replace facts, formulas, options or solutions.
Generation works offline without AI. See [QUESTION_GENERATION.md](QUESTION_GENERATION.md).

The supported library is finite. CS facts can be exhausted. Difficulty labels are
curated by structure. The dashboard reports first-exposure accuracy and a
provisional observed band after 30 responses; psychometric calibration still
requires a real validation study. New domains and richer models are deliberate extensions, not generated
mathematical structures automatically trusted by the application.

## Runtime

`docker-compose.yml` runs PostgreSQL, persistent Redis, a migration service,
FastAPI, a Celery worker, one Beat scheduler, and a Next.js standalone server.
Only the web port is exposed, bound to the laptop's loopback address. The browser
uses `/api`; a server-side proxy resolves the API address at runtime. The database,
Redis and API do not need public laptop ports.

```powershell
docker compose ps
docker compose logs --tail=100 api worker scheduler web
docker compose down
docker compose up -d --wait
```

Ordinary shutdown preserves named volumes. **`docker compose down -v` deletes the
local database and Redis volume; do not use it to troubleshoot startup.**

## Development and validation

Python 3.11+ and Node 22+ are supported for native development. Direct dependencies
are in `backend/requirements.in`; `backend/requirements.txt` is the universal,
hash-verified runtime lock. Frontend dependencies use `package-lock.json`.

```powershell
py -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\backend\.venv\Scripts\python.exe -m pytest tests/test_model_generation.py tests/test_passwords.py -q
cd frontend
npm ci
npm run build
```

PostgreSQL integration tests require an explicitly supplied disposable database
name ending in `_test`; they clear its application tables. Browser tests create
candidate accounts and admin assessment/batch data. Run them only on a disposable
installation. Detailed commands and observed results are in
[VALIDATION.md](VALIDATION.md).

This version targets a tested local workflow. External Google/Gemini integrations
require your own configuration and were not live-tested without credentials.
Windows PowerShell initialization was validated with PowerShell on Linux; Docker
Desktop/WSL 2 and your laptop itself must still be checked when we run it there.
Historical progress notes are retained under `docs/history/` and are not current
setup instructions.
