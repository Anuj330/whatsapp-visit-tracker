"""FastAPI app tracking whether a WhatsApp bot user is returning."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session

from .db import engine, get_session, init_db
from .models import (
    User,
    UserResponse,
    VisitCheckRequest,
    VisitCheckResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database schema on startup."""
    init_db()
    yield


app = FastAPI(title="WhatsApp Visit Tracker", lifespan=lifespan)


def _utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    """Attach UTC tzinfo to a naive datetime read back from SQLite."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/visits/check", response_model=VisitCheckResponse)
def check_visit(
    payload: VisitCheckRequest,
    session: Session = Depends(get_session),
) -> VisitCheckResponse:
    """Record a visit for a phone number, atomically.

    Inserts the user on first contact (is_returning=false) or increments
    their visit_count and refreshes last_seen_at otherwise (is_returning=true).
    The work is done as a single INSERT ... ON CONFLICT DO UPDATE so two
    concurrent first-hits cannot double-create the row.
    """
    now = _utcnow()
    # Pick the dialect-specific INSERT so ON CONFLICT works on both the
    # SQLite used locally/in tests and the Postgres used in production.
    dialect = session.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    stmt = (
        insert(User)
        .values(
            phone=payload.phone,
            first_seen_at=now,
            last_seen_at=now,
            visit_count=1,
        )
        .on_conflict_do_update(
            index_elements=["phone"],
            set_={
                "last_seen_at": now,
                "visit_count": User.visit_count + 1,
            },
        )
        .returning(
            User.phone,
            User.first_seen_at,
            User.last_seen_at,
            User.visit_count,
        )
    )

    row = session.exec(stmt).one()
    session.commit()

    # visit_count only ever increments, so >1 reliably means a returning user.
    return VisitCheckResponse(
        phone=row.phone,
        is_returning=row.visit_count > 1,
        first_seen_at=_as_utc(row.first_seen_at),
        last_seen_at=_as_utc(row.last_seen_at),
        visit_count=row.visit_count,
    )


@app.get("/users/{phone}", response_model=UserResponse)
def get_user(
    phone: str,
    session: Session = Depends(get_session),
) -> UserResponse:
    """Return the stored record for a phone number, or 404 if absent."""
    user = session.get(User, phone)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return UserResponse(
        phone=user.phone,
        first_seen_at=_as_utc(user.first_seen_at),
        last_seen_at=_as_utc(user.last_seen_at),
        visit_count=user.visit_count,
    )
