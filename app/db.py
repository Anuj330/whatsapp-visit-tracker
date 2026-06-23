"""Database engine and session setup.

Works with both SQLite (local dev / tests) and PostgreSQL (production on a
free hosted DB such as Neon or Supabase). The database is chosen entirely via
the DATABASE_URL environment variable.
"""

import os

from sqlmodel import Session, SQLModel, create_engine


def _normalize_url(url: str) -> str:
    """Ensure Postgres URLs use the psycopg (v3) driver.

    Hosted providers hand out ``postgres://`` or ``postgresql://`` URLs;
    SQLAlchemy needs an explicit ``+psycopg`` suffix to pick the v3 driver.
    """
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _normalize_url(os.getenv("DATABASE_URL", "sqlite:///./users.db"))

# check_same_thread is a SQLite-only flag; it lets the connection be shared
# across the threads Uvicorn may use. Postgres takes no such argument.
_connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(DATABASE_URL, connect_args=_connect_args)


def init_db() -> None:
    """Create tables if they do not already exist."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    """FastAPI dependency that yields a database session."""
    with Session(engine) as session:
        yield session
