"""Database engine, session factory, and Base.

MVP uses SQLite; the same models run on Postgres by changing NHAC_DATABASE_URL.
``init_db()`` creates tables for dev; a production deploy would use migrations.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from nhac.config import settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    connect_args = {}
    if settings.is_sqlite:
        # Ensure the parent dir exists and allow use across threads (uvicorn).
        db_path = settings.database_url.replace("sqlite:///", "")
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False}
    return create_engine(settings.database_url, connect_args=connect_args, future=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create all tables (dev convenience). Import models first so they register."""
    from nhac import models  # noqa: F401  (registers mappers on Base.metadata)

    Base.metadata.create_all(bind=engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a session and always closes it."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
