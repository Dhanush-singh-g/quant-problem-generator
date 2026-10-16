-- QuantForge practice-mode history + revision saves.
-- Run after MIGRATION_FINAL_PASS.sql on existing PostgreSQL/Supabase databases.

CREATE TABLE IF NOT EXISTS user_question_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question_id VARCHAR(36) NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    first_seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMP NOT NULL DEFAULT NOW(),
    seen_count INTEGER NOT NULL DEFAULT 1,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    incorrect_count INTEGER NOT NULL DEFAULT 0,
    last_correct BOOLEAN NULL,
    saved BOOLEAN NOT NULL DEFAULT FALSE,
    saved_at TIMESTAMP NULL,
    CONSTRAINT uq_user_question_history UNIQUE (user_id, question_id)
);

CREATE INDEX IF NOT EXISTS ix_user_question_history_user_id
    ON user_question_history(user_id);
CREATE INDEX IF NOT EXISTS ix_user_question_history_question_id
    ON user_question_history(question_id);
CREATE INDEX IF NOT EXISTS ix_user_question_history_saved
    ON user_question_history(user_id, saved, last_seen_at DESC);

-- Efficient unseen-question lookup starts from the existing question pool index
-- and anti-joins against uq_user_question_history(user_id, question_id).
