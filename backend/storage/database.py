"""SQLAlchemy engine, session factory, and dependency for FastAPI."""

from collections.abc import Generator
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.config import get_config

Base = declarative_base()

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def get_engine():
    """Create or return the shared SQLAlchemy engine (SQLite)."""
    global _engine
    if _engine is None:
        config = get_config()
        url = getattr(config, "database_url", None) or f"sqlite:///{config.sqlite_path}"
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False} if "sqlite" in url else {},
        )
    return _engine


def get_session_factory():
    """Return session factory (create after engine)."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a DB session and close after request."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Create all tables (e.g. at startup). Call after get_engine()."""
    from backend.storage import models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    # Add inbox_email to processings if missing (migration for existing DBs)
    if "sqlite" in str(engine.url):
        from sqlalchemy import text
        try:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE processings ADD COLUMN inbox_email VARCHAR(255)"))
        except Exception:
            # Column may already exist
            pass
