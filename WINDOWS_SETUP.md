# Windows laptop setup and upgrades

## Recommended: Docker Desktop

Use Windows 10/11 with WSL 2 enabled and Docker Desktop running **Linux containers**.
Allow enough free disk for images, the database, and builds; allocating around
4 GB of memory to Docker is a reasonable starting point for this local stack.
Keep the extracted project outside a heavily synced OneDrive folder when possible
to avoid sync contention and file locking during builds.

From PowerShell in the extracted project folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

`Bypass` applies to this PowerShell process so the downloaded local script can run;
it does not change the machine's execution policy. Read the script before running
it if required by your computer's policy. Do not disable corporate security policy.

The script creates `.env` only if absent, checks Docker/Compose, starts services
in dependency/health order, runs migrations, and adds starter inventory. It never
prints generated secrets and never overwrites an existing `.env`.

Open http://localhost:3000. Find admin credentials in `.env`, sign in, and create a
separate candidate account for normal practice. Gemini and Google sign-in are
optional. Do not upload or send `.env` in chat.

### Common startup problems

- **Docker not found / daemon unavailable:** install or start Docker Desktop, wait
  for its engine to be ready, and select Linux containers.
- **Port 3000 in use:** choose another `WEB_PORT` in `.env` and change
  `CORS_ORIGINS` to the same browser origin, for example
  `WEB_PORT=3002` and `CORS_ORIGINS=http://localhost:3002`. Restart with
  `docker compose up -d --wait`, then open that origin.
- **Old `.env` missing a setting:** compare its variable names with `.env.example`.
  Add missing variables without replacing existing secrets. The Docker stack uses
  its private database/Redis, even if native URLs exist in `.env`.
- **A service is unhealthy:** run `docker compose ps` and
  `docker compose logs --tail=100 api migrate worker scheduler web`. Fix the
  reported cause; do not delete database volumes as a first step.
- **Downloads fail:** check Docker Desktop DNS, VPN/proxy and trusted CA settings.
  Keep TLS verification enabled. BuildKit supports an optional `build_ca` secret
  for an approved enterprise CA; this certificate is not retained in the image.
- **No questions for a selection:** use a smaller set, another topic or explicit
  revision mode. The admin factory can generate more supported questions.
- **Another tab changed a set:** reload that set to recover the latest server
  draft. Unsubmitted edits in the stale tab are not authoritative.

### Safe restart and backup

```powershell
docker compose down
docker compose up -d --wait
```

Do not add `-v` to `down` unless you deliberately want to delete all local data.
To create a binary database backup without PowerShell's text-redirection encoding:

```powershell
docker compose exec -T postgres pg_dump -U quant -d quantforge -Fc -f /tmp/quantforge.backup
docker compose cp postgres:/tmp/quantforge.backup .\quantforge.backup
```

The backup contains user and attempt data; store it privately.

## Existing database upgrade

The bundled Docker environment creates a separate local database. It does not
connect to or modify an existing Supabase/hosted database. For a native upgrade:

1. Back up the existing database and retain the old source/configuration.
2. Stop the old API, workers and scheduler. Record any old, untracked generation
   requests for resubmission through the new batch API.
3. Install the locked dependencies and configure `DATABASE_URL` and `REDIS_URL`
   securely for the intended instance. Keep the previous JWT/assignment secrets
   where needed for existing assessment presentation, and require a new sign-in
   after this authentication update.
4. From `backend/`, run `python -m app.migrate`. Versioned migration checksums
   prevent already-applied files from silently changing. Existing original
   migrations remain ordered before the application/batch migrations.
5. Run `python -m app.audit_inventory` for a read-only report, then
   `python -m app.audit_inventory --apply` in maintenance mode to approve supported
   valid questions, rebuild logical identities, and quarantine invalid/duplicate
   items. No question or past attempt is deleted. Previously active sets and
   historical reviews retain their referenced questions.
6. Restart the API, one scheduler and the workers. Resubmit old generation requests
   through the new dashboard. Add starter inventory with `python -m app.seed` if
   desired. Audit/seed are explicit operations, not automatic production actions.

Legacy inventory begins with `review_status=pending`; it does not enter new sets
until audited. Some previously AI-enhanced wording may fail the stricter gate and
need manual review. Existing deactivated questions stay deactivated.

## Native development (optional)

Install Python 3.11+ and Node 22+. Supply reachable PostgreSQL and Redis services;
Celery needs Redis and the application requires PostgreSQL. In `.env`, configure
`DATABASE_URL`, `REDIS_URL`, strong separate secrets, admin bootstrap credentials,
`CORS_ORIGINS=http://localhost:3000`, and development cookie settings. Set
`AUTO_CREATE_SCHEMA=true` for automatic local migrations, or run migrations first.

```powershell
py -m venv backend/.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
if (-not (Test-Path frontend/.env.local)) { Copy-Item frontend/.env.local.example frontend/.env.local }
```

Activate the Python environment in three separate terminals and run from `backend/`:

```powershell
uvicorn app.main:app --reload
```

```powershell
celery -A app.workers.celery_app:celery worker --pool=solo -Q generation --loglevel=info
```

```powershell
celery -A app.workers.celery_app:celery beat --schedule=quantforge-beat --loglevel=info
```

From `frontend/`: `npm ci`, then `npm run dev`. The default server-side proxy
connects to `http://127.0.0.1:8000`. Set `API_INTERNAL_URL` in
`frontend/.env.local` if the API runs elsewhere. Remove any legacy
`NEXT_PUBLIC_API_URL` setting so the browser uses the same-origin proxy. Do not put API/database secrets
in `NEXT_PUBLIC_*` variables. Windows solo workers have fewer process time-limit
guarantees than Linux prefork workers; Docker is the recommended laptop path.

## Optional integrations

Google sign-in requires matching `GOOGLE_CLIENT_ID` and
`NEXT_PUBLIC_GOOGLE_CLIENT_ID`, plus authorized browser origins in Google's client
configuration. Rebuild the web image after changing a public Google client ID.
Gemini context needs `GEMINI_API_KEY`, an available `GEMINI_MODEL`, and
`GENERATION_USE_AI_CONTEXT=true`. Missing credentials, timeouts and rate limits
fall back to reviewed canonical wording. Core functionality needs neither service.
