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
    make_phone_group_id,
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
    """Record a visit for a phone number within a group, atomically.

    The user is keyed by phone_group_id = "{phone}_{group_id}", so the same
    number is tracked separately per group. Inserts the user on first contact
    (is_returning=false) or increments their visit_count and refreshes
    last_seen_at otherwise (is_returning=true). The work is done as a single
    INSERT ... ON CONFLICT DO UPDATE so two concurrent first-hits cannot
    double-create the row.
    """
    now = _utcnow()
    phone_group_id = make_phone_group_id(payload.phone, payload.group_id)
    # Pick the dialect-specific INSERT so ON CONFLICT works on both the
    # SQLite used locally/in tests and the Postgres used in production.
    dialect = session.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    stmt = (
        insert(User)
        .values(
            phone_group_id=phone_group_id,
            phone=payload.phone,
            group_id=payload.group_id,
            first_seen_at=now,
            last_seen_at=now,
            visit_count=1,
        )
        .on_conflict_do_update(
            index_elements=["phone_group_id"],
            set_={
                "last_seen_at": now,
                "visit_count": User.visit_count + 1,
            },
        )
        .returning(
            User.phone_group_id,
            User.phone,
            User.group_id,
            User.first_seen_at,
            User.last_seen_at,
            User.visit_count,
        )
    )

    row = session.exec(stmt).one()
    session.commit()

    # visit_count only ever increments, so >1 reliably means a returning user.
    return VisitCheckResponse(
        phone_group_id=row.phone_group_id,
        phone=row.phone,
        group_id=row.group_id,
        is_returning=row.visit_count > 1,
        first_seen_at=_as_utc(row.first_seen_at),
        last_seen_at=_as_utc(row.last_seen_at),
        visit_count=row.visit_count,
    )


@app.get("/users/{phone_group_id}", response_model=UserResponse)
def get_user(
    phone_group_id: str,
    session: Session = Depends(get_session),
) -> UserResponse:
    """Return the stored record by phone_group_id, or 404 if absent."""
    user = session.get(User, phone_group_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return UserResponse(
        phone_group_id=user.phone_group_id,
        phone=user.phone,
        group_id=user.group_id,
        first_seen_at=_as_utc(user.first_seen_at),
        last_seen_at=_as_utc(user.last_seen_at),
        visit_count=user.visit_count,
    )
