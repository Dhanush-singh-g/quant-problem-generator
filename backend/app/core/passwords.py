"""Argon2id for new passwords; read-only compatibility with existing bcrypt hashes."""
import base64
import hashlib
import hmac
import re

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

hasher = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)
LEGACY = re.compile(r"^\$bcrypt-sha256\$(?:(?:v=2,t=(2[ab]),r=(\d+))|(?:(2[ab]),(\d+)))\$([./A-Za-z0-9]{22})\$([./A-Za-z0-9]{31})$")


def hash_password(value):
    return hasher.hash(value)


def verify_password(value, hashed):
    try:
        if hashed.startswith("$argon2"):
            return hasher.verify(hashed, value)
        raw = value.encode("utf-8")
        match = LEGACY.fullmatch(hashed)
        if match:
            v2_type, v2_rounds, v1_type, v1_rounds, salt, digest = match.groups()
            rounds = int(v2_rounds or v1_rounds)
            if not 4 <= rounds <= 16:
                return False
            prehash = hmac.digest(salt.encode("ascii"), raw, "sha256") if v2_type else hashlib.sha256(raw).digest()
            bcrypt_hash = f"${v2_type or v1_type}${rounds:02d}${salt}{digest}".encode("ascii")
            return bcrypt.checkpw(base64.b64encode(prehash), bcrypt_hash)
        if re.match(r"^\$2[aby]\$\d{2}\$", hashed):
            # Match historical bcrypt's byte truncation for migration only.
            return bcrypt.checkpw(raw[:72], hashed.encode("ascii"))
    except (ValueError, TypeError, InvalidHashError, VerificationError):
        return False
    return False
