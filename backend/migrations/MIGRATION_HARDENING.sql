-- Run once in Supabase SQL Editor before using this hardened build.
ALTER TABLE questions ALTER COLUMN answer_value TYPE TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub VARCHAR(255);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub ON users (google_sub) WHERE google_sub IS NOT NULL;
DROP INDEX IF EXISTS uq_assessment_question;
ALTER TABLE assessment_question_assignments DROP CONSTRAINT IF EXISTS uq_assessment_question;
CREATE INDEX IF NOT EXISTS ix_questions_pool_lookup ON questions (active, domain, difficulty);
