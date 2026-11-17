"""Current-user dependency. Prompt 11 replaces this one file with real login."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from hwai.config import get_settings
from hwai.db import get_db
from hwai.errors import ApiError
from hwai.models import User

DEV_EMAIL = "dev@local"


def current_user(db: Annotated[Session, Depends(get_db)]) -> User:
    if get_settings().env != "dev":
        raise ApiError(401, "unauthorized", "Please log in.")
    user = db.scalar(select(User).where(User.email == DEV_EMAIL))
    if user is None:
        user = User(email=DEV_EMAIL)
        db.add(user)
        db.commit()
    return user
