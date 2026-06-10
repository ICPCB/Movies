from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.db_models import Base


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "cinematch.db"
DATABASE_URL = os.getenv(
    "CINEMATCH_DB_URL",
    f"sqlite+pysqlite:///{DEFAULT_DB_PATH.as_posix()}",
)

_engine_kwargs: dict = {"future": True}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
if DATABASE_URL in {"sqlite://", "sqlite:///:memory:", "sqlite+pysqlite:///:memory:"}:
    _engine_kwargs["poolclass"] = StaticPool

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    del connection_record
    if not DATABASE_URL.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def create_all() -> None:
    if DATABASE_URL.startswith("sqlite") and ":memory:" not in DATABASE_URL:
        DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
