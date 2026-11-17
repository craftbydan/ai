"""SQLite wiring."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from hwai.config import get_settings


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    data_dir = get_settings().data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(data_dir / 'hwai.sqlite').resolve()}"


def make_engine() -> Engine:
    return create_engine(database_url(), connect_args={"check_same_thread": False})


_engines: dict[str, Engine] = {}


def new_session() -> Session:
    """A new session on the cached engine for the current DATA_DIR (caller closes it)."""
    url = database_url()
    engine = _engines.get(url)
    if engine is None:
        engine = _engines[url] = make_engine()
    return sessionmaker(engine, expire_on_commit=False)()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with new_session() as session:
        yield session
