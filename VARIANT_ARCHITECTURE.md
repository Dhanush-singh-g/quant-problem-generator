# Reusable Assessment Variant Architecture

## Goal

Scale candidate delivery without generating a unique LLM paper for every user and without putting Gemini or question generation on the candidate critical path.

## Assessment creation

The admin chooses topics, Easy/Medium/Hard counts, expected candidates and a target candidates-per-variant value. The backend first creates one immutable slot-level blueprint.

```text
variant_count = ceil(expected_candidates / candidates_per_variant)
```

`MAX_ASSESSMENT_VARIANTS` bounds generation/storage cost.

## Variant materialization

Before an assessment becomes active, FastAPI materializes `assessment_variants` and `assessment_variant_questions`. Each variant obeys the same blueprint. Questions are selected from validated topic/difficulty pools and a single paper is not allowed to contain the same question twice.

Pool generation belongs to the control plane. Celery replenishes inventory asynchronously through Redis. A deterministic local fill can satisfy a control-plane shortage without making candidate start depend on Gemini.

## Candidate assignment

Candidate mapping is deterministic and non-obvious:

```text
HMAC-SHA256(ASSIGNMENT_SECRET, assessment_id:user_id) % variant_count
```

The chosen `variant_number` is persisted in `assessment_sessions`.

## O(1) candidate-start writes

A new session also stores `presentation_seed`. Question order and option-letter mapping are reconstructed deterministically from:

```text
variant_number + presentation_seed
```

Therefore a 100-question assessment still needs one candidate session insert at start rather than 100 candidate-assignment inserts. Legacy per-question assignment rows remain supported only for migration compatibility.

## Hot path

```text
Authenticated request
 -> indexed assessment lookup
 -> HMAC variant selection
 -> indexed variant/question lookup
 -> one session insert
 -> deterministic in-process shuffle
 -> response
```

No Gemini request, Celery job, question generation or full-table random query occurs on this path.

## Storage responsibilities

- **PostgreSQL** — users, questions, immutable blueprints, variants, candidate sessions, answers, scores and review data.
- **Redis** — Celery broker, distributed auth/start limits, shared AI response cache, AI quota coordination and operational counters.
- **Celery** — asynchronous pool replenishment.
- **Gemini** — optional background neutral context enhancement only; never the answer authority.

## Capacity model

For `C` candidates, `Q` questions per paper and `V` variants:

- variant-question rows scale roughly as `V × Q`
- start-time session rows scale as `C`
- submitted answer/detail payload volume necessarily scales with `C × Q`
- expensive generation work is bounded by `V` and the reusable question pool rather than by `C`

Example: 100,000 candidates, 20 questions and 100 variants require about 2,000 variant-question rows plus 100,000 candidate session rows, rather than two million unique generated questions or two million start-time assignment rows.

## Horizontal scaling

FastAPI replicas are stateless beyond shared PostgreSQL/Redis. Sticky sessions are not required. Keep `JWT_SECRET` and `ASSIGNMENT_SECRET` consistent across replicas and size each process's SQL pool against the managed database connection budget. Multiple Celery workers can be scaled independently.

For much larger deployments, add PgBouncer/managed pooling, a load balancer, centralized observability, load tests and a WAF/rate-limit edge layer.

## Fairness

Every variant follows the same topic/difficulty slot blueprint. Structural difficulty is curated but not psychometrically calibrated. Empirical item-response data is required before claiming statistical equivalence between all items in the same tier.
