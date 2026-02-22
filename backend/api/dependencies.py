"""FastAPI dependencies: DB session, config."""

from typing import Generator

from sqlalchemy.orm import Session

from backend.config import get_config
from backend.storage.database import get_db as _get_db


def get_db() -> Generator[Session, None, None]:
    """Yield a DB session for the request."""
    yield from _get_db()


def get_config_dep():
    """Return app config (for dependency injection)."""
    return get_config()
