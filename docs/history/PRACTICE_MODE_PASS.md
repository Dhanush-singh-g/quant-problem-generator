# Practice Mode Pass

This iteration changes QuantForge's primary product surface from a one-off aptitude assessment into an ongoing practice platform while keeping the asynchronous AI Question Factory independent from delivery.

## Valid difficulty reassignment

A Gemini generation job still asks for a target band, but difficulty is determined by the deterministic classifier. If a job requests Hard and the verified result is actually Medium, the question is no longer discarded solely because of the mismatch. It is stored as Medium if its exact logical content is not already in PostgreSQL. Metadata records both the requested and stored difficulty. Invalid mathematics, failed verification, malformed proposals, bad distractors, and true duplicates are still rejected.

## No-repeat practice

`user_question_history` has a unique `(user_id, question_id)` key. A question is recorded as seen when it is delivered, not when the user submits, so abandoning a session does not make it eligible again. Practice selection excludes every question already present in that user's history. If unseen inventory is insufficient, the API asks the background factory to replenish the relevant pool rather than silently repeating questions.

## Saved revision questions

The same history row contains `saved` and `saved_at`. Users can save a question during practice, including using the "Couldn't solve · save & skip" action, and review saved questions later. Attempt/correct/incorrect counters are retained for the later adaptive-practice iteration.

## Frontend positioning

The landing page now explains the product before practice begins: asynchronous AI generation, deterministic verification, no-repeat delivery, revision saves, continuous replenishment, and difficulty reclassification. The primary navigation is Practice / Saved / Progress rather than assessment-first.

## Migration

Existing PostgreSQL/Supabase deployments should run `MIGRATION_PRACTICE_MODE.sql` after the prior migrations. Development with `AUTO_CREATE_SCHEMA=true` can create the new table from the SQLAlchemy model automatically.
