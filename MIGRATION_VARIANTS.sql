-- QuantForge reusable assessment-variant migration.
-- Run once in Supabase SQL Editor AFTER MIGRATION_HARDENING.sql.

ALTER TABLE assessments ADD COLUMN IF NOT EXISTS blueprint JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE assessments ADD COLUMN IF NOT EXISTS expected_candidates INTEGER NOT NULL DEFAULT 500;
ALTER TABLE assessments ADD COLUMN IF NOT EXISTS candidates_per_variant INTEGER NOT NULL DEFAULT 25;
ALTER TABLE assessments ADD COLUMN IF NOT EXISTS variant_count INTEGER NOT NULL DEFAULT 20;

ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS variant_number INTEGER;
CREATE INDEX IF NOT EXISTS ix_assessment_sessions_variant_number ON assessment_sessions (variant_number);

ALTER TABLE assessment_question_assignments ADD COLUMN IF NOT EXISTS option_map JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS assessment_variants (
    id SERIAL PRIMARY KEY,
    assessment_id VARCHAR(36) NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    variant_number INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_assessment_variant_number UNIQUE (assessment_id, variant_number)
);
CREATE INDEX IF NOT EXISTS ix_assessment_variants_assessment_id ON assessment_variants (assessment_id);

CREATE TABLE IF NOT EXISTS assessment_variant_questions (
    id SERIAL PRIMARY KEY,
    variant_id INTEGER NOT NULL REFERENCES assessment_variants(id) ON DELETE CASCADE,
    question_id VARCHAR(36) NOT NULL REFERENCES questions(id),
    position INTEGER NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_variant_position UNIQUE (variant_id, position)
);
CREATE INDEX IF NOT EXISTS ix_assessment_variant_questions_variant_id ON assessment_variant_questions (variant_id);
CREATE INDEX IF NOT EXISTS ix_assessment_variant_questions_question_id ON assessment_variant_questions (question_id);

-- Helps variant preparation fetch recent validated questions without ORDER BY random().
CREATE INDEX IF NOT EXISTS ix_questions_pool_recent
ON questions (active, domain, difficulty, created_at DESC);
