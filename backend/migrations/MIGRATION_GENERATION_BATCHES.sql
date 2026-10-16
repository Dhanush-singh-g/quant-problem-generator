-- Apply after MIGRATION_PRACTICE_MODE.sql. Safe to rerun on PostgreSQL.
BEGIN;
CREATE TABLE IF NOT EXISTS generation_buckets (
    domain VARCHAR(120) NOT NULL,
    difficulty VARCHAR(20) NOT NULL,
    PRIMARY KEY (domain, difficulty)
);
CREATE TABLE IF NOT EXISTS generation_batches (
    id VARCHAR(36) PRIMARY KEY,
    requested_by INTEGER NOT NULL REFERENCES users(id),
    domain VARCHAR(120) NOT NULL,
    difficulty VARCHAR(20) NOT NULL,
    requested_count INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_generation_batches_requested_by ON generation_batches(requested_by);
CREATE INDEX IF NOT EXISTS ix_generation_batches_created_at ON generation_batches(created_at);
CREATE TABLE IF NOT EXISTS generation_jobs (
    id VARCHAR(36) PRIMARY KEY,
    batch_id VARCHAR(36) NOT NULL REFERENCES generation_batches(id) ON DELETE CASCADE,
    domain VARCHAR(120) NOT NULL,
    difficulty VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMP NOT NULL DEFAULT NOW(),
    lease_until TIMESTAMP NULL,
    dispatch_token VARCHAR(36) NULL,
    question_id VARCHAR(36) NULL REFERENCES questions(id) ON DELETE SET NULL,
    error_code VARCHAR(80) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_generation_job_status CHECK (status IN ('pending','queued','running','succeeded','rejected','failed'))
);
CREATE INDEX IF NOT EXISTS ix_generation_jobs_dispatch ON generation_jobs(domain, difficulty, status, available_at);
CREATE INDEX IF NOT EXISTS ix_generation_jobs_batch ON generation_jobs(batch_id, status);
COMMIT;
