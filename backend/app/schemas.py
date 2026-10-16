from typing import Literal
from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_validator


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Name must contain at least two characters")
        return value.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class GoogleLoginRequest(BaseModel):
    credential: str = Field(min_length=20, max_length=8192)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    role: str


class AuthResponse(BaseModel):
    # JWT is intentionally delivered only through the HttpOnly cookie.
    user: UserPublic


class QuestionPublic(BaseModel):
    id: str
    domain: str
    difficulty: str
    story_text: str
    options: dict[str, str]


class QuizResponse(BaseModel):
    session_id: str
    questions: list[QuestionPublic]
    source: str


class PracticeStart(BaseModel):
    count: int = Field(default=5, ge=1, le=20)
    domain: str = "ALL"
    difficulty: str = "ALL"
    mode: Literal["unseen", "revision"] = "unseen"


class SessionDraft(BaseModel):
    answers: dict[str, Literal["A", "B", "C", "D"]] = Field(default_factory=dict, max_length=100)
    current_index: int = Field(default=0, ge=0, le=99)
    revision: int = Field(ge=0)


class AnswerItem(BaseModel):
    question_id: str = Field(min_length=1, max_length=64)
    selected_option: str = Field(min_length=1, max_length=1, pattern=r"^[A-Da-d]$")


class SubmitQuiz(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    answers: list[AnswerItem] = Field(default_factory=list, max_length=100)
    duration_seconds: int = Field(default=0, ge=0)


class AnswerResult(BaseModel):
    question_id: str
    selected_option: str
    correct_option: str
    correct: bool
    solution: str


class QuizResult(BaseModel):
    score: int | None
    total: int
    results: list[AnswerResult]
    insights: dict | None = None
    review_available: bool = True


class AssessmentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    duration_minutes: int = Field(ge=1, le=240)
    easy_count: int = Field(default=0, ge=0, le=100)
    medium_count: int = Field(default=0, ge=0, le=100)
    hard_count: int = Field(default=0, ge=0, le=100)
    domains: list[str] = Field(min_length=1, max_length=50)
    expected_candidates: int = Field(default=500, ge=1, le=100000)
    candidates_per_variant: int = Field(default=25, ge=5, le=1000)


class AssessmentPublic(BaseModel):
    id: str
    title: str
    duration_minutes: int
    easy_count: int
    medium_count: int
    hard_count: int
    domains: list[str]
    status: str
    total_questions: int
    expected_candidates: int
    candidates_per_variant: int
    variant_count: int
    blueprint: list[dict]


class AssessmentStartResponse(BaseModel):
    session_id: str
    assessment: AssessmentPublic
    started_at: str
    deadline_at: str
    duration_seconds: int
    questions: list[QuestionPublic]
    answers: dict[str, str] = Field(default_factory=dict)
    current_index: int = 0
    revision: int = 0


class AssessmentSubmit(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    answers: list[AnswerItem] = Field(default_factory=list, max_length=100)


class LeaderboardRow(BaseModel):
    rank: int
    user_id: int
    name: str
    score: int
    total: int
    duration_seconds: int
    submitted_at: str


class SaveQuestionRequest(BaseModel):
    saved: bool = True


class ManualGenerationRequest(BaseModel):
    domain: str
    difficulty: str = Field(pattern=r"^(easy|medium|hard)$")
    count: int = Field(default=5, ge=1, le=100)
