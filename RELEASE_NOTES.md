# QuantForge complete local release — v6

This package supersedes the earlier generation-only ZIP. It includes the full
uploaded application plus the generation and application fixes described below.

## Generation and inventory

- 21 supported quantitative models, including three new multi-stage structures.
- Canonical and independent answer/unit checks, immutable solutions, validated
  options and stable logical identities.
- Optional AI chooses reviewed context; unsupported AI formulas cannot be published.
- Durable batch/jobs, concurrency control, retries and stale-worker recovery.
- Batch progress and approved inventory dashboard.
- Read-only inventory audit plus an explicit apply mode that quarantines invalid
  or duplicate questions without deleting referenced attempt history.
- Provisional first-exposure difficulty observations, separate from curated bands.
- Offline, repeatable starter inventory.

## Candidate and admin flows

- Shared authentication state updates navigation immediately on login/logout.
- Argon2id passwords with tested legacy-hash migration and revocable account tokens.
- Server-persisted practice answers, position, result review and tab conflicts.
- Per-account inventory counts, smaller set sizes and explicit revision mode.
- Correct answered/completed/wrong/skipped profile totals and server elapsed time.
- Saved-answer privacy, save/remove failure handling, pagination and mobile links.
- Complete assessment creation/preview/activation and candidate screens, saved
  drafts, resume, authoritative expiry, delayed review and leaderboards.
- Same-origin API proxy with runtime internal address and readable API errors.

## Installation and verification

- Updated and locked application dependencies; audits reported zero known advisories.
- Hash-verified universal Python runtime/development locks and npm lockfile.
- Versioned migrations, health-ordered Docker startup and persistent service volumes.
- Windows setup script generates independent secrets, preserves existing .env,
  starts all services and seeds approved questions without external AI accounts.
- Current setup/validation documentation replaces earlier working notes, which
  are retained under docs/history.

Validation includes 79 automated tests, production browser scenarios, a fresh
container build, migrations, seed repeatability, preserved data across container
recreation, and a small concurrent request burst. Details and reproducible
commands are in VALIDATION.md. The next verification is Docker Desktop/WSL 2 on
the user's laptop. Optional live Google/Gemini require user-specific configuration;
this release does not claim exhaustive bug absence or production certification.
