# Security and operational scope

## Implemented controls

- New passwords use Argon2id. Read-only compatibility supports existing bcrypt and
  both bcrypt-sha256 formats; successful password login upgrades legacy hashes.
- JWT validation fixes HS256 and requires issuer, audience, subject, issued-at,
  expiry and account token version. Logout invalidates existing account tokens.
- HttpOnly cookies carry authentication; database roles authorize every admin
  request. Browser state only controls presentation.
- Cookie-authenticated writes require an allowed Origin. Bearer API clients use
  explicit authentication rather than ambient browser cookies.
- Authentication and start limits use Redis. Redis operations have connection/read
  timeouts. Local setup configures fail-closed rate limiting.
- Practice/assessment drafts and results are scoped to the authenticated user.
  Conflicting drafts, foreign question IDs and duplicate answer IDs are rejected.
- Timers and scoring are server-authoritative. Saved questions do not reveal a
  solution until its practice set has been completed.
- Generation uses reviewed models and independent checks. Unrestricted experimental
  AI modules have no production publication route. Pending/quarantined questions
  cannot enter newly created sets or assessment variants.
- SQL migrations are versioned and checksum-checked under a database lock. Runtime
  Python dependencies are pinned with artifact hashes; frontend uses a lockfile.
- Docker runtime processes use unprivileged application users. Only the web port
  is published, on loopback; database, Redis and API stay on the private network.
- ZIP packaging excludes credentials, caches, local databases and test traces.

## Deployment boundaries

The supplied Compose configuration is a local laptop environment. Public hosting
requires HTTPS, production settings/secure cookies, appropriate origin and proxy
configuration, backups and monitoring for that deployment. Local Docker credentials
are generated per installation and should not be reused elsewhere.

The dependency audits passed with no known advisories at validation time. Audits
must be repeated as advisories change; this is not a guarantee of absence of flaws.

Google login and Gemini require account-specific configuration. Their negative
paths and controlled responses are tested; live credentials were not supplied.
Question difficulty remains structurally curated. The optional first-exposure
statistics are provisional observations, not validated ability estimates.

The worker architecture supports additional replicas, but this release is tested
for local use and short concurrent bursts. It is not represented as load-tested
for thousands of candidates. Run one Beat scheduler per installation. Choose
worker/bucket concurrency and database pools together; queued jobs keep their
place in PostgreSQL rather than being discarded at a concurrency cap.
