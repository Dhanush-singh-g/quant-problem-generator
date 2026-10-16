-- Additive application fixes; no questions, attempts, or user accounts are deleted.
ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS review_status VARCHAR(20) NOT NULL DEFAULT 'pending';
CREATE INDEX IF NOT EXISTS ix_questions_review_status ON questions(review_status);
ALTER TABLE user_question_history ADD COLUMN IF NOT EXISTS completed_count INTEGER NOT NULL DEFAULT 0;
UPDATE user_question_history h SET completed_count = 1
WHERE completed_count = 0 AND EXISTS (
    SELECT 1 FROM question_assignments qa JOIN quiz_sessions qs ON qs.id = qa.session_id
    WHERE qa.question_id = h.question_id AND qs.user_id = h.user_id AND qs.status = 'submitted'
);
ALTER TABLE quiz_sessions ADD COLUMN IF NOT EXISTS mode VARCHAR(20) NOT NULL DEFAULT 'unseen';
ALTER TABLE quiz_sessions ADD COLUMN IF NOT EXISTS answers JSON NOT NULL DEFAULT '{}';
ALTER TABLE quiz_sessions ADD COLUMN IF NOT EXISTS current_index INTEGER NOT NULL DEFAULT 0;
ALTER TABLE quiz_sessions ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE quiz_sessions ADD COLUMN IF NOT EXISTS result JSON NOT NULL DEFAULT '{}';
-- Preserve the latest legacy active session for resume; older sessions remain in history.
WITH ranked AS (
    SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC, id) AS n
    FROM quiz_sessions WHERE status = 'active'
)
UPDATE quiz_sessions SET status = 'abandoned' WHERE id IN (SELECT id FROM ranked WHERE n > 1);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_practice_user ON quiz_sessions(user_id) WHERE status = 'active';
ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS current_index INTEGER NOT NULL DEFAULT 0;
ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 0;
