from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "QuantForge API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://quant:quant@postgres:5432/quantforge"
    redis_url: str = "redis://redis:6379/0"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    ai_rpm: int = 8
    question_pool_floor: int = 20
    generation_quality_attempts: int = Field(default=3, ge=1, le=25)
    generation_max_pending_per_bucket: int = Field(default=5, ge=1, le=100)
    generation_retry_backoff_seconds: int = Field(default=20, ge=1)
    generation_use_ai_context: bool = False
    generation_max_job_attempts: int = Field(default=3, ge=1, le=25)
    generation_lease_seconds: int = Field(default=180, ge=150)
    cors_origins: str = "http://localhost:3000"

    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 480
    jwt_issuer: str = "quantforge-api"
    jwt_audience: str = "quantforge-web"
    assignment_secret: str | None = None
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    admin_email: str = "admin@example.com"
    admin_password: str = "ChangeMe123!"
    bootstrap_admin: bool = True
    google_client_id: str | None = None

    auth_rate_limit_per_minute: int = 20
    account_auth_rate_limit_per_minute: int = 10
    start_rate_limit_per_minute: int = 30
    rate_limit_fail_open: bool = True
    enable_practice_mode: bool = True
    reveal_results_while_active: bool = True

    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout_seconds: int = 10

    max_assessment_variants: int = 100
    min_question_choices_per_slot: int = 6
    auto_create_schema: bool = True

    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / ".env.local"),
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def allowed_origins(self) -> list[str]:
        return [x.strip().rstrip("/") for x in self.cors_origins.split(",") if x.strip()]

    @property
    def auth_cookie_name(self) -> str:
        # __Host- cookies cannot be scoped to a parent domain and therefore
        # resist cookie tossing/fixation from sibling subdomains.
        return "__Host-qf_token" if self.is_production else "qf_token"

    def validate_security(self) -> None:
        if self.cookie_samesite not in {"lax", "strict", "none"}:
            raise RuntimeError("COOKIE_SAMESITE must be lax, strict, or none")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise RuntimeError("SameSite=None cookies require Secure")
        if self.is_production:
            if len(self.jwt_secret) < 32 or self.jwt_secret == "change-me-in-production":
                raise RuntimeError("Production requires a strong JWT_SECRET of at least 32 characters")
            if not self.assignment_secret or len(self.assignment_secret) < 32:
                raise RuntimeError("Production requires a separate ASSIGNMENT_SECRET of at least 32 characters")
            if self.assignment_secret == self.jwt_secret:
                raise RuntimeError("ASSIGNMENT_SECRET must differ from JWT_SECRET in production")
            if not self.cookie_secure:
                raise RuntimeError("COOKIE_SECURE=true is required in production")
            if "*" in self.allowed_origins:
                raise RuntimeError("Wildcard CORS is not allowed with credential cookies in production")
            if not self.allowed_origins or any(not origin.startswith("https://") for origin in self.allowed_origins):
                raise RuntimeError("Production CORS_ORIGINS must contain explicit HTTPS origins")
            if self.bootstrap_admin and self.admin_password == "ChangeMe123!":
                raise RuntimeError("Change ADMIN_PASSWORD before production")
            if self.cookie_samesite == "none" and not self.cookie_secure:
                raise RuntimeError("SameSite=None cookies require Secure")


settings = Settings()
