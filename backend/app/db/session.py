"""Engine and session management.

Synchronous SQLAlchemy on purpose: database work here is short and indexed,
while the real latency lives in LLM inference, which is handled with async
HTTP. FastAPI runs sync dependencies in a threadpool, so this does not block
the event loop, and it keeps Alembic and the test fixtures simple.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # transparently recycle connections the DB dropped
    pool_size=10,
    max_overflow=20,
    echo=settings.debug and settings.app_env == "development",
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session that always gets closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database() -> bool:
    """Cheap liveness probe used by the readiness endpoint."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
