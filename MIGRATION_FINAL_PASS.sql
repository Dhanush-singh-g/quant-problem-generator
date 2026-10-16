-- QuantForge final-pass migration.
-- Run AFTER MIGRATION_HARDENING.sql and MIGRATION_VARIANTS.sql.
-- Safe to rerun.

-- Logical duplicate prevention for newly generated questions.
ALTER TABLE questions ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS uq_questions_content_hash
ON questions (content_hash) WHERE content_hash IS NOT NULL;

-- Clean any legacy duplicate candidate assignments before enforcing uniqueness.
DELETE FROM assessment_question_assignments a
USING assessment_question_assignments b
WHERE a.id > b.id
  AND a.session_id = b.session_id
  AND a.question_id = b.question_id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_assessment_session_question
ON assessment_question_assignments (session_id, question_id);

-- Clean any legacy duplicate question inside a reusable paper variant.
DELETE FROM assessment_variant_questions a
USING assessment_variant_questions b
WHERE a.id > b.id
  AND a.variant_id = b.variant_id
  AND a.question_id = b.question_id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_variant_question
ON assessment_variant_questions (variant_id, question_id);

-- Normalize old state if more than one assessment was left active.
WITH keep AS (
    SELECT id
    FROM assessments
    WHERE status = 'active'
    ORDER BY activated_at DESC NULLS LAST, created_at DESC
    LIMIT 1
)
UPDATE assessments
SET status = 'closed', closed_at = COALESCE(closed_at, NOW())
WHERE status = 'active'
  AND id NOT IN (SELECT id FROM keep);

-- Database-level guard: only one assessment may be active at a time.
CREATE UNIQUE INDEX IF NOT EXISTS uq_single_active_assessment
ON assessments ((status)) WHERE status = 'active';


-- O(1) candidate-start write path: presentation order and option mapping are
-- reconstructed from this per-session seed instead of storing one assignment
-- row per question for every candidate. Legacy assignment rows remain readable.
ALTER TABLE assessment_sessions
ADD COLUMN IF NOT EXISTS presentation_seed VARCHAR(64);

-- Supports ordered/paginated leaderboards at large candidate counts.
CREATE INDEX IF NOT EXISTS ix_assessment_sessions_leaderboard
ON assessment_sessions (
    assessment_id,
    status,
    score DESC,
    duration_seconds ASC,
    submitted_at ASC
);

-- Common candidate resume/status lookup.
CREATE INDEX IF NOT EXISTS ix_assessment_sessions_candidate_lookup
ON assessment_sessions (assessment_id, user_id, status);
