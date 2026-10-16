# Setup and operations

## Windows: first run

Install Docker Desktop, enable WSL 2, and use Linux containers. Extract the project outside OneDrive. Open PowerShell in the folder containing `docker-compose.yml`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Open http://localhost:3000. Read administrator credentials privately with `notepad .env`. The script preserves existing configuration, applies migrations, and seeds starter inventory.

## Common fixes

| Symptom | Action |
| --- | --- |
| Script not found | Open the extracted inner folder containing `scripts/setup.ps1` |
| Docker unavailable | Start Docker Desktop; check Linux-container mode |
| Port 3000 occupied | Set `WEB_PORT=3002` and `CORS_ORIGINS=http://localhost:3002` in `.env`; restart Compose |
| Service unhealthy | Run `docker compose logs --tail=100 api migrate worker scheduler web` |
| Insufficient questions | Request a smaller set, use revision mode, or generate inventory as admin |
| Stale-tab conflict | Reload to restore the latest saved draft |

## Stop, restart, backup

```powershell
docker compose down
docker compose up -d --wait
docker compose exec -T postgres pg_dump -U quant -d quantforge -Fc -f /tmp/quantforge.backup
docker compose cp postgres:/tmp/quantforge.backup ./quantforge.backup
```

Named volumes retain data across normal shutdown. `down -v` deletes them. Backups contain private user data; keep off-server copies and test restores before depending on them.

## Optional integrations

Gemini: set `GENERATION_USE_AI_CONTEXT=true`, `GEMINI_API_KEY`, and an available `GEMINI_MODEL` in `.env`, then run `docker compose up -d --force-recreate --wait`. It selects reviewed context only. Never use a `NEXT_PUBLIC_*` variable for secrets.

Google login: configure the same web client ID in `GOOGLE_CLIENT_ID` and `NEXT_PUBLIC_GOOGLE_CLIENT_ID`, authorize the browser origin in Google, and rebuild the web image. Neither integration is required for core functionality.

## Public deployment

Use an Ubuntu server with Docker Engine/Compose and a domain. A small deployment can start around 2 CPUs and 4 GB RAM; this is not a measured capacity guarantee.

1. Clone branch `quantforge-complete-v6` from the repository.
2. Create a private `.env` from `.env.example`. Generate fresh, separate random database, JWT, assignment, and administrator secrets; do not reuse laptop credentials.
3. Set `ENVIRONMENT=production`, `COOKIE_SECURE=true`, and `CORS_ORIGINS=https://YOUR_DOMAIN`. Set your administrator email and retain `COOKIE_SAMESITE=lax`.
4. Run `docker compose up -d --build --wait --wait-timeout 300`.
5. Seed with `docker compose exec -T api python -m app.seed --per-bucket 10`.
6. Point domain DNS at the server. Install Caddy on the host and configure:

```caddyfile
YOUR_DOMAIN {
    reverse_proxy 127.0.0.1:3000
}
```

7. Validate/reload Caddy. Allow inbound HTTP/HTTPS and your SSH port. Keep database, Redis, and API private.
8. Verify login, practice resume/submission, generation progress, and assessment expiry over HTTPS. Configure backups and monitoring before relying on the deployment.

Run one Beat scheduler. This is a single-server setup; public deployment has not been validated on your chosen provider.

## Native development

Use Python 3.11+, Node 22+, PostgreSQL, and Redis. Install `backend/requirements-dev.txt` and run `npm ci` in `frontend/`. Configure reachable `DATABASE_URL`/`REDIS_URL` and secrets in root `.env`.

From `backend/`, with the Python environment activated, run migrations and start these in separate terminals:

```text
python -m app.migrate
uvicorn app.main:app --reload
celery -A app.workers.celery_app:celery worker --pool=solo -Q generation --loglevel=info
celery -A app.workers.celery_app:celery beat --schedule=quantforge-beat --loglevel=info
```

Run `npm run dev` in `frontend/`. Its proxy defaults to `http://127.0.0.1:8000`; override `API_INTERNAL_URL` if needed. Remove legacy `NEXT_PUBLIC_API_URL`. Windows solo workers have weaker time-limit guarantees than Linux prefork workers.

## Existing database upgrades

Back up first; stop old API/workers/scheduler. Run `python -m app.migrate` from `backend/` using the intended database configuration. Do not modify applied SQL migration files: their checksums are recorded.

Run `python -m app.audit_inventory` for a report, then `python -m app.audit_inventory --apply` in maintenance mode to approve supported inventory and quarantine invalid/duplicate items. Historical records are retained. Resubmit any old untracked generation requests. Restart services and verify before reopening access.

The bundled Compose stack always uses its private local PostgreSQL/Redis; native hosted URLs do not redirect it to your existing database.
