"""SQLite wiring. Tables arrive in later prompts."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

from hwai.config import get_settings


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    data_dir = get_settings().data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(data_dir / 'hwai.sqlite').resolve()}"


def make_engine() -> Engine:
    return create_engine(database_url())
