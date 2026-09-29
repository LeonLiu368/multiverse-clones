"""SQLite engine / session helpers."""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def get_engine(path: str | None = None) -> Engine:
    """Engine for a SQLite file (defaults to env ``SLACK_DB`` or ``slack.db``)."""
    path = path or os.environ.get("SLACK_DB", "slack.db")
    return create_engine(f"sqlite:///{path}", future=True)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)
