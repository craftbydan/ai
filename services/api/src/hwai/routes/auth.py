"""Signup, login, logout and 'who am I'."""

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from hwai.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    hash_password,
    make_session_token,
    verify_password,
)
from hwai.config import get_settings
from hwai.deps import DbDep, UserDep
from hwai.errors import ApiError
from hwai.models import User

router = APIRouter()

MIN_PASSWORD = 10


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD, max_length=256)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class MeOut(BaseModel):
    id: str
    email: str


def _set_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        COOKIE_NAME,
        make_session_token(user.id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=get_settings().env != "dev",
        path="/",
    )


@router.post("/auth/signup", response_model=MeOut, status_code=201)
def signup(body: Credentials, response: Response, db: DbDep) -> User:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise ApiError(409, "email_taken", "That email already has an account. Try logging in.")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "email_taken", "That email already has an account.") from None
    _set_cookie(response, user)
    return user


@router.post("/auth/login", response_model=MeOut)
def login(body: LoginBody, request: Request, response: Response, db: DbDep) -> User:
    email = body.email.lower()
    ip = request.client.host if request.client else "unknown"
    limiter = request.app.state.login_limiter
    if limiter.blocked(email, ip):
        raise ApiError(
            429, "rate_limited", "Too many failed attempts. Please wait 10 minutes and try again."
        )
    user = db.scalar(select(User).where(User.email == email))
    if not verify_password(user.password_hash if user else None, body.password) or user is None:
        limiter.record_failure(email, ip)
        raise ApiError(401, "invalid_credentials", "Email or password is not right.")
    limiter.reset(email, ip)
    _set_cookie(response, user)
    return user


@router.post("/auth/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")


@router.get("/auth/me", response_model=MeOut)
def me(user: UserDep) -> User:
    return user
