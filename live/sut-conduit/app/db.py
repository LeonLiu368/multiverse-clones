"""Database engine + session wiring.

The SQLAlchemy engine pool_size is read from the DB_POOL_SIZE env var at
process start. This is the P4 fault surface: DB_POOL_SIZE=1 serializes all DB
work onto a single connection (healthy at rest, collapses under concurrent
load). The remediation is `dokku config:set conduit DB_POOL_SIZE=<sane>`, which
triggers a redeploy and rebuilds the engine with a larger pool.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Dokku/Heroku-style: default to a local dev URL, override via DATABASE_URL.
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg2://conduit:conduit@localhost:5432/conduit"
)
# SQLAlchemy needs the psycopg2 driver spelled out; accept a bare postgres:// too.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://", "postgresql+psycopg2://", 1
    )

# ---- THE FAULT KNOB -------------------------------------------------------
# Runtime env var, NOT a code constant. Wired straight into the engine pool.
DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "10"))
# Keep max_overflow at 0 so DB_POOL_SIZE is a hard ceiling on concurrent
# connections -> the serialization is sharp and measurable under load.
DB_MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", "0"))
# Seconds a request will wait for a free connection before erroring (503-ish).
DB_POOL_TIMEOUT = int(os.environ.get("DB_POOL_TIMEOUT", "5"))
# ---------------------------------------------------------------------------

engine = create_engine(
    DATABASE_URL,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
