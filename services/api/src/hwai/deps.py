"""Annotated dependency aliases shared by routes."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from hwai.auth import current_user
from hwai.db import get_db
from hwai.models import User

DbDep = Annotated[Session, Depends(get_db)]
UserDep = Annotated[User, Depends(current_user)]
