from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from ..models import User

from .passwords import hash_password, verify_password

bearer = HTTPBearer(auto_error=False)


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {
            "sub": str(user.id),
            "ver": user.token_version,
            "iat": now,
            "exp": exp,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
):
    raw = creds.credentials if creds else request.cookies.get(settings.auth_cookie_name)
    if not raw:
        raise HTTPException(401, "Authentication required")
    try:
        payload = jwt.decode(
            raw,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "ver", "iat", "exp", "iss", "aud"]},
        )
        uid = int(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError, TypeError):
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(User, uid)
    if not user or payload["ver"] != user.token_version:
        raise HTTPException(401, "Session has expired; sign in again")
    return user


def admin_user(user: User = Depends(current_user)):
    # Role is read from the database on every request; a stale JWT cannot retain
    # admin access after the database role is revoked.
    if user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return user
