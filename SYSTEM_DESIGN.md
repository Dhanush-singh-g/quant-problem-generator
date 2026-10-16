# System design

```text
Browser -> Next.js UI and same-origin /api proxy -> FastAPI -> PostgreSQL
                                                       |        |
                                                       |        +-- users, reviewed questions
                                                       |        +-- resumable practice/assessment sessions
                                                       |        +-- attempts, saved history, batch/job records
                                                       |
                                                       +-> Redis -> Celery workers
                                                           ^            |
                                                           |            +-- reviewed model/fact generation
                                                           |            +-- independent validation and publication
                                                           +-- one Beat dispatcher
```

The browser never receives database credentials or AI keys. The Next.js proxy
reads `API_INTERNAL_URL` on the server at runtime and forwards cookie authentication
without baking a browser-facing backend hostname into the bundle.

## Practice lifecycle

An explicit POST creates one active set per account. PostgreSQL account/unique
locks prevent concurrent starts from consuming multiple sets. Questions are
recorded as delivered, but only completed sets remove them from normal inventory.
Answers and navigator position autosave with optimistic revisions. Conflicting
browser tabs must reload. Submission locks the session, scores assigned questions
on the server, persists a durable result and returns that same result on retry.

Practice distinguishes completed, answered and skipped questions. Revision is
explicit. Saved solutions stay locked until completion. Server timestamps measure
elapsed time, including periods away from the browser. User-supplied duration is
retained only as a compatibility field and never trusted for new statistics.

## Assessment lifecycle

An administrator previews a topic/difficulty blueprint, creates a draft and
activates it after reusable variants have been prepared. Activation is serialized
and only one assessment is globally active. A candidate's HMAC-selected variant,
presentation seed and deadline persist; reconstructed option order survives
refresh. Draft updates stop at the deadline. A late submission scores only the
previously saved answers. Closing an assessment stops new starts, while existing
sessions can finish. Review follows the configured release policy.

## Question Factory

PostgreSQL stores all requested generation jobs; Redis transports notifications.
Per-bucket database locks coordinate concurrency across dispatchers. Leases and
dispatch tokens recover interrupted workers and prevent stale publication. The
question and successful job outcome commit together. The dashboard reports each
terminal outcome instead of treating requested work as accepted inventory.

New publication requires a supported model or curated fact, a canonical solution,
independent answer/unit verification, distinct options and a logical duplicate
check. Optional AI selects reviewed neutral context. Existing inventory uses a
read-only audit/apply workflow; invalid items are quarantined, not deleted.

Observed item statistics use the first submitted unseen response per user/item,
exclude revision attempts, and require at least 30 responses for a provisional
band. They never silently relabel curated models and are not a psychometric study.
