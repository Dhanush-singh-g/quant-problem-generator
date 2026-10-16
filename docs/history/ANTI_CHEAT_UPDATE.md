# Anti-cheating architecture

QuantForge does not generate one AI paper per candidate and does not serve one globally cached paper to everybody. Formal assessments use a bounded pool of reusable variants plus candidate-specific deterministic presentation.

## Layers

1. **Common blueprint** — every variant follows the same topic and difficulty slots.
2. **Reusable paper variants** — different variants fill those slots with different validated question IDs where inventory permits.
3. **Non-obvious assignment** — candidate-to-variant mapping uses HMAC-SHA256 with a server-side `ASSIGNMENT_SECRET`.
4. **Candidate-specific question order** — reconstructed from the candidate session `presentation_seed`.
5. **Candidate-specific option order** — each MCQ's displayed A/B/C/D mapping is independently reconstructed from the same seed.
6. **Immutable session identity** — one `(assessment_id, user_id)` session exists; refresh/resume returns the same paper/presentation.
7. **Server scoring** — the client never receives canonical answers before review is allowed.
8. **Server deadline** — browser timers are display-only.
9. **Optional delayed review** — production can keep scores/solutions hidden until the assessment is closed and live sessions finish.

Candidates may share an underlying variant at large scale. That is intentional. Their displayed order and option labels still differ, and generating a unique LLM paper per person is avoided because it adds cost, latency and unnecessary correctness risk.

## Scalable session representation

New formal sessions do not insert one presentation row per question. PostgreSQL stores the candidate's `variant_number` and `presentation_seed`; the API reconstructs the exact question/option presentation when starting, resuming, submitting or reviewing.

Legacy `assessment_question_assignments` rows remain readable so older attempts are not broken during migration.

## Leaderboard

Ranking is:

1. score descending
2. server-measured completion time ascending
3. submission timestamp ascending

The leaderboard is paginated and supported by a composite PostgreSQL index.
