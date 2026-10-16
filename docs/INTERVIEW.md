# Interview answers

## Explain the project in 30 seconds

“QuantForge is a practice and assessment platform for quantitative aptitude and computer science. It supports resumable practice, timed exams, analytics, and background question generation. The main design decision is to generate mathematics from reviewed models and verify it independently rather than trusting an LLM's answer. PostgreSQL stores durable state, Redis transports tasks, and Celery processes generation outside candidate requests.”

## Is this an AI question generator?

The current production generator is primarily model/template based. Python samples parameters and computes answers. Optional Gemini selects one of four reviewed context phrases. It does not invent mathematical structures, calculate answers, or grade users. Do not describe it as an unrestricted AI generator.

## Why templates instead of asking Gemini directly?

They provide reproducible answers, controlled parameter ranges, predictable cost, and offline operation. The tradeoff is limited structural variety: changing numbers does not create a new reasoning pattern.

## How do you check correctness?

A canonical solver generates the answer. A separate verifier recomputes it. Publication also checks model support, parameter bounds, units, option uniqueness, canonical solution, and duplicates. These checks reduce errors; they are not a proof that every model or question is flawless.

## Why FastAPI and Next.js?

FastAPI keeps the API close to the Python generation logic. Next.js provides the interface and a same-origin server proxy. This separates UI concerns from authentication, scoring, and persistence.

## Why both PostgreSQL and Redis?

PostgreSQL stores durable, transactional records. Redis provides queue transport, shared rate limits, and caches. Losing a queue notification must not erase the underlying generation request.

## Why Celery?

Generation can outlast a normal request and may need retries. The API records a batch and returns; workers process it asynchronously while the dashboard polls progress.

## What happens if a worker crashes or a task is delivered twice?

Database jobs have leases and reservation tokens. Expired reservations can be recovered. Stale workers cannot publish against a newer reservation. Question creation and job success commit together. The design handles redelivery; it does not assume exactly-once message delivery.

## How do you prevent duplicate questions?

A stable fingerprint represents logical content. Quantitative identity includes the model and numeric parameters but excludes cosmetic names/context. CS identity uses the curated fact. This prevents exact logical duplicates, not every semantically similar question.

## How does refresh preserve a candidate's work?

Answers and position are saved to PostgreSQL. Reloading restores the session. Revision numbers reject stale updates from another tab. Unsaved edits can still be lost if the browser closes before the save succeeds.

## How do you prevent duplicate scoring?

Submission locks the session and persists its result. Retried submissions return the stored result rather than creating another attempt.

## How are timed exams enforced?

The server stores the deadline and controls scoring. After expiry, only answers saved before the deadline are scored. Changing the browser timer does not extend the exam.

## How are assessment variants assigned?

Variants follow one topic/difficulty blueprint. HMAC-based assignment selects a variant, and a persisted presentation seed reconstructs order. This reduces per-candidate generation/storage work; it does not prove psychometric equivalence or prevent all cheating.

## What security controls matter here?

Argon2id password hashes, HttpOnly authentication cookies, JWT validation, server-side role/ownership checks, allowed-Origin checks for cookie writes, rate limits, and server-authoritative scoring. Secrets remain outside the frontend bundle.

## What has actually been tested?

The recorded validation includes 79 automated tests, 2,100 quantitative model samples, production frontend builds, and two end-to-end browser scenarios. These are previous release results, not a new run for this documentation update. See VALIDATION.md for reproduction and limits.

## Can it handle thousands of concurrent users?

That has not been demonstrated. The architecture permits separate API/worker scaling, but connection pools, database indexes, queue latency, and candidate submission bursts need load testing first. One Compose server is not high availability.

## What would you improve next?

Add reviewed models and facts, validate difficulty with real response data, load-test exam starts/submissions, and add deployment monitoring, tested restores, and high availability where justified. Expand AI only behind a correctness boundary that can independently verify its output.

## What was your personal contribution?

Describe only work you actually performed and understand: requirements, model design, implementation, testing, or deployment. Explain how AI-assisted work was reviewed. Do not claim sole authorship or independently implemented features you cannot defend.
