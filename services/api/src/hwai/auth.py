"""Accounts: password hashing, signed session cookies, login rate limit, current_user().

The session is a signed (itsdangerous) cookie holding only the user id. It is HTTP-only and
same-site=lax. The dev stub user exists only when ENV=dev and DEV_USER=1.
"""

import logging
import secrets
import threading
import time
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from hwai.config import Settings, get_settings
from hwai.db import get_db
from hwai.errors import ApiError
from hwai.models import User

log = logging.getLogger("hwai.auth")

DEV_EMAIL = "dev@local"
COOKIE_NAME = "hwai_session"
SESSION_MAX_AGE = 14 * 24 * 3600
_SALT = "hwai-session-v1"

_hasher = PasswordHasher()
_dev_key = secrets.token_urlsafe(32)  # per-process, dev only, never persisted


def dev_stub_enabled(settings: Settings) -> bool:
    return settings.env == "dev" and settings.dev_user


def signing_key(settings: Settings) -> str:
    """The cookie signing key: SECRET_KEY, or (ENV=dev only) a per-process random key."""
    if settings.secret_key:
        return settings.secret_key
    if settings.env == "dev":
        return _dev_key
    raise RuntimeError("SECRET_KEY is required when ENV is not 'dev'. Set it in .env.")


def check_startup_settings(settings: Settings) -> None:
    """Fail startup (clear message, no secret values printed) on an unsafe configuration."""
    key = settings.stripe_secret_key
    if key and not key.startswith("sk_test_"):
        raise RuntimeError(
            "STRIPE_SECRET_KEY must be a Stripe TEST key starting with 'sk_test_'. "
            "Live keys are not accepted by this app (see Launch gate in CLAUDE.md)."
        )
    if not settings.secret_key:
        if settings.env != "dev":
            raise RuntimeError("SECRET_KEY is required when ENV is not 'dev'. Set it in .env.")
        log.warning(
            "SECRET_KEY is not set: using an INSECURE per-process random dev key. "
            "Sessions are lost on restart. Never run like this outside ENV=dev."
        )
    if settings.env != "dev" and settings.billing == "off":
        log.warning("BILLING=off is ignored because ENV is not 'dev'.")
    if settings.env != "dev" and settings.dev_user:
        log.warning("DEV_USER is ignored because ENV is not 'dev'.")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-ish work even for unknown users (hash None) so timing does not reveal them."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(signing_key(settings), salt=_SALT)


def make_session_token(user_id: str) -> str:
    return _serializer(get_settings()).dumps({"uid": user_id})


def read_session_token(token: str) -> str | None:
    try:
        data = _serializer(get_settings()).loads(token, max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None
    uid = data.get("uid") if isinstance(data, dict) else None
    return uid if isinstance(uid, str) else None


class LoginRateLimiter:
    """5 failed logins per 10 minutes per (email, IP), kept in memory."""

    def __init__(self, limit: int = 5, window_s: int = 600) -> None:
        self.limit = limit
        self.window_s = window_s
        self._fails: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: tuple[str, str]) -> list[float]:
        cutoff = time.monotonic() - self.window_s
        fresh = [t for t in self._fails.get(key, []) if t > cutoff]
        if fresh:
            self._fails[key] = fresh
        else:
            self._fails.pop(key, None)
        return fresh

    def blocked(self, email: str, ip: str) -> bool:
        with self._lock:
            return len(self._recent((email, ip))) >= self.limit

    def record_failure(self, email: str, ip: str) -> None:
        with self._lock:
            self._recent((email, ip))
            self._fails.setdefault((email, ip), []).append(time.monotonic())

    def reset(self, email: str, ip: str) -> None:
        with self._lock:
            self._fails.pop((email, ip), None)


def current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    settings = get_settings()
    token = request.cookies.get(COOKIE_NAME)
    if token:
        uid = read_session_token(token)
        user = db.get(User, uid) if uid else None
        if user is not None:
            return user
    if dev_stub_enabled(settings):
        user = db.scalar(select(User).where(User.email == DEV_EMAIL))
        if user is None:
            user = User(email=DEV_EMAIL)
            db.add(user)
            db.commit()
        return user
    raise ApiError(401, "unauthorized", "Please log in.")
