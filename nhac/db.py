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


# Columns added after the first release. ``create_all`` only creates missing
# TABLES, so pre-existing dev databases need these back-filled with ALTER.
# (A production deploy would use Alembic; this keeps local DBs working.)
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "clips": {"montage_key": "TEXT"},
}


def _ensure_added_columns() -> None:
    if not settings.is_sqlite:
        return  # non-SQLite deploys should manage schema with real migrations
    from sqlalchemy import inspect, text

    with engine.begin() as conn:
        inspector = inspect(conn)
        for table, columns in _ADDED_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            for name, ddl_type in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))


def init_db() -> None:
    """Create all tables (dev convenience). Import models first so they register."""
    from nhac import models  # noqa: F401  (registers mappers on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _ensure_added_columns()


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a session and always closes it."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
