from contextlib import asynccontextmanager
import re
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .core.config import settings
from .core.db import Base, engine, SessionLocal
from .core.auth import hash_password
from .models import User
from .api.routes import router
from .api.practice import router as practice_router

settings.validate_security()

def startup():
    # Local convenience only. Production should use migrations and set
    # AUTO_CREATE_SCHEMA=false so multiple replicas do not race on DDL.
    if settings.auto_create_schema:
        from .migrate import migrate
        migrate(engine)

    if settings.bootstrap_admin:
        with SessionLocal() as db:
            if not db.scalar(select(User).where(User.email == settings.admin_email.lower())):
                db.add(
                    User(
                        email=settings.admin_email.lower(),
                        name="QuantForge Admin",
                        password_hash=hash_password(settings.admin_password),
                        role="admin",
                    )
                )
                try:
                    db.commit()
                except IntegrityError:
                    # Another replica may have created the bootstrap account first.
                    db.rollback()


@asynccontextmanager
async def lifespan(app):
    startup()
    yield


app = FastAPI(
    title=settings.app_name,
    version="6.0.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # Cookie-authenticated state-changing browser requests must originate from
    # the configured frontend. Bearer-token API clients are not subject to CSRF.
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not request.headers.get("authorization", "").lower().startswith("bearer "):
        origin = (request.headers.get("origin") or "").rstrip("/")
        if (origin and origin not in settings.allowed_origins) or (request.cookies.get(settings.auth_cookie_name) and not origin):
            return JSONResponse({"detail": "Untrusted request origin"}, status_code=403)

    incoming_request_id = request.headers.get("x-request-id", "")
    request_id = incoming_request_id if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", incoming_request_id) else uuid.uuid4().hex

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.include_router(router)
app.include_router(practice_router)


