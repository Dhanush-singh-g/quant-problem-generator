from datetime import datetime
from sqlalchemy import String, Integer, DateTime, JSON, Boolean, Text, ForeignKey, UniqueConstraint, Index, CheckConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (Index("ix_questions_pool_lookup", "active", "domain", "difficulty"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    domain: Mapped[str] = mapped_column(String(120), index=True)
    difficulty: Mapped[str] = mapped_column(String(20), index=True, default="easy")
    story_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    options: Mapped[dict] = mapped_column(JSON)
    correct_option: Mapped[str] = mapped_column(String(1))
    canonical_solution: Mapped[str] = mapped_column(Text)
    answer_value: Mapped[str] = mapped_column(Text)
    answer_unit: Mapped[str] = mapped_column(String(30), default="")
    variables: Mapped[dict] = mapped_column(JSON)
    generation_metadata: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class UserQuestionHistory(Base):
    """Cross-session practice history used for no-repeat delivery and revision saves."""

    __tablename__ = "user_question_history"
    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_user_question_history"),
        Index("ix_user_question_history_saved", "user_id", "saved", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    seen_count: Mapped[int] = mapped_column(Integer, default=1)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0)
    last_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # The composite saved-history index above already covers this query path.
    # index=True here would generate the same index name and break fresh DDL.
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    saved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    question: Mapped[Question] = relationship()


class QuizSession(Base):
    """A quiz assignment created before the candidate submits answers."""

    __tablename__ = "quiz_sessions"
    __table_args__ = (Index("uq_active_practice_user", "user_id", unique=True,
                           postgresql_where=text("status = 'active'")),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    domain: Mapped[str] = mapped_column(String(120), default="ALL", index=True)
    difficulty: Mapped[str] = mapped_column(String(20), index=True)
    question_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    mode: Mapped[str] = mapped_column(String(20), default="unseen")
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    assignments: Mapped[list["QuestionAssignment"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class QuestionAssignment(Base):
    """
    Practice-mode question assignment.

    Practice questions may be reused across users. Formal assessments use the
    reusable variant tables below and keep each candidate session immutable.
    """

    __tablename__ = "question_assignments"
    __table_args__ = (UniqueConstraint("session_id", "position", name="uq_session_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("quiz_sessions.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    session: Mapped[QuizSession] = relationship(back_populates="assignments")
    question: Mapped[Question] = relationship()


class Assessment(Base):
    """Admin-defined assessment blueprint."""

    __tablename__ = "assessments"
    __table_args__ = (Index("uq_single_active_assessment", "status", unique=True,
                           postgresql_where=text("status = 'active'")),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    easy_count: Mapped[int] = mapped_column(Integer, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, default=0)
    hard_count: Mapped[int] = mapped_column(Integer, default=0)
    domains: Mapped[list] = mapped_column(JSON)
    blueprint: Mapped[list] = mapped_column(JSON, default=list)
    expected_candidates: Mapped[int] = mapped_column(Integer, default=500)
    candidates_per_variant: Mapped[int] = mapped_column(Integer, default=25)
    variant_count: Mapped[int] = mapped_column(Integer, default=20)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AssessmentSession(Base):
    """A candidate's immutable question assignment for one assessment."""

    __tablename__ = "assessment_sessions"
    __table_args__ = (UniqueConstraint("assessment_id", "user_id", name="uq_assessment_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    deadline_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int] = mapped_column(Integer)
    variant_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    presentation_seed: Mapped[str | None] = mapped_column(String(64), nullable=True)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[list] = mapped_column(JSON, default=list)

    assignments: Mapped[list["AssessmentQuestionAssignment"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class AssessmentQuestionAssignment(Base):
    """Legacy persisted presentation rows retained for migration compatibility.

    New formal assessment sessions reconstruct presentation deterministically
    from variant_number + presentation_seed and do not write one row per question.
    """

    __tablename__ = "assessment_question_assignments"
    __table_args__ = (
        UniqueConstraint("session_id", "position", name="uq_assessment_session_position"),
        UniqueConstraint("session_id", "question_id", name="uq_assessment_session_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("assessment_sessions.id", ondelete="CASCADE"), index=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    option_map: Mapped[dict] = mapped_column(JSON, default=dict)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    session: Mapped[AssessmentSession] = relationship(back_populates="assignments")
    question: Mapped[Question] = relationship()


class AssessmentVariant(Base):
    """Pre-generated paper variant reused by many candidates."""

    __tablename__ = "assessment_variants"
    __table_args__ = (UniqueConstraint("assessment_id", "variant_number", name="uq_assessment_variant_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    variant_number: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AssessmentVariantQuestion(Base):
    """A slot in a reusable assessment paper variant."""

    __tablename__ = "assessment_variant_questions"
    __table_args__ = (
        UniqueConstraint("variant_id", "position", name="uq_variant_position"),
        UniqueConstraint("variant_id", "question_id", name="uq_variant_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("assessment_variants.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    answers: Mapped[dict] = mapped_column(JSON)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class GenerationBucket(Base):
    """Database row lock coordinates concurrency across API/worker replicas."""
    __tablename__ = "generation_buckets"
    domain: Mapped[str] = mapped_column(String(120), primary_key=True)
    difficulty: Mapped[str] = mapped_column(String(20), primary_key=True)


class GenerationBatch(Base):
    __tablename__ = "generation_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    domain: Mapped[str] = mapped_column(String(120))
    difficulty: Mapped[str] = mapped_column(String(20))
    requested_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('pending','queued','running','succeeded','rejected','failed')", name="ck_generation_job_status"),
        Index("ix_generation_jobs_dispatch", "domain", "difficulty", "status", "available_at"),
        Index("ix_generation_jobs_batch", "batch_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("generation_batches.id", ondelete="CASCADE"))
    domain: Mapped[str] = mapped_column(String(120))
    difficulty: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dispatch_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    question_id: Mapped[str | None] = mapped_column(ForeignKey("questions.id", ondelete="SET NULL"), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
