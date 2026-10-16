# QuantForge

A quantitative aptitude and computer-science practice platform with resumable practice, timed assessments, performance analytics, and an administrator question factory.

## Run locally

Install Docker Desktop with WSL 2 and Linux containers. In the project folder, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Open http://localhost:3000. Read `ADMIN_EMAIL` and `ADMIN_PASSWORD` from the generated `.env`; register a separate candidate account for practice. Keep `.env` private.

The script builds services, runs migrations, and seeds starter questions. Python, Node, PostgreSQL, Redis, and Gemini accounts are not required separately.

```powershell
docker compose ps                       # Service status
docker compose logs --tail=100 api web worker scheduler
docker compose down                     # Stop; retain data
docker compose up -d --wait              # Restart
```

Never use `down -v` unless you intend to delete stored data.

## What generates the questions?

Python generates questions from **21 reviewed quantitative models** and a curated CS fact bank. Canonical and independent solvers check answers before publication. Optional Gemini selects a reviewed context phrase; it does not invent questions, solve them, or grade candidates.

## Project guide

- [Architecture](docs/ARCHITECTURE.md): components, request flows, correctness, and tradeoffs.
- [Interview answers](docs/INTERVIEW.md): project explanation and technical questions.
- [Setup and operations](docs/SETUP.md): troubleshooting, backup, optional integrations, and deployment.
- [Validation](docs/VALIDATION.md): recorded checks, test commands, and limits.

## Source map

| Location | Responsibility |
| --- | --- |
| `frontend/` | Next.js UI and same-origin API proxy |
| `backend/app/` | FastAPI routes, authentication, persistence, Celery jobs |
| `core/` | Quantitative models, canonical solver, independent verifier |
| `services/` | Publication validation, controlled AI context, supporting services |
| `agents/` | Generation/validation helpers; not autonomous AI agents |
| `data/` | Reviewed model rules and curated CS facts |
| `tests/` | Model, security, persistence, and job-recovery tests |
| `scripts/` | Setup and offline validation |

PostgreSQL is the source of truth. Redis handles queue transport, rate limiting, and caches. The supplied Compose stack is a single-machine deployment, not a high-availability service.
