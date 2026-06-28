"""FastAPI app tracking whether a WhatsApp bot user is returning."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, select

from .db import get_session, init_db
from .models import (
    User,
    UserGroup,
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


def _group_ids_for(session: Session, phone: str) -> list[str]:
    """Return the sorted list of group_ids (regions) a phone is saved to."""
    rows = session.exec(
        select(UserGroup.group_id).where(UserGroup.phone == phone)
    ).all()
    return sorted(rows)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/visits/check", response_model=VisitCheckResponse)
def check_visit(
    payload: VisitCheckRequest,
    session: Session = Depends(get_session),
) -> VisitCheckResponse:
    """Record a visit for a phone number and the group it came from.

    The phone is the key (one row per number). On first contact the number is
    inserted (is_returning=false); otherwise visit_count is incremented and
    last_seen_at refreshed (is_returning=true). The group_id from this request
    is added to the number's set of groups (regions). Both writes happen in one
    transaction, and each uses INSERT ... ON CONFLICT so concurrent first-hits
    cannot double-create rows. The response lists every region the number is
    saved to.
    """
    now = _utcnow()
    # Pick the dialect-specific INSERT so ON CONFLICT works on both the
    # SQLite used locally/in tests and the Postgres used in production.
    dialect = session.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert

    # 1. Upsert the user row, incrementing the visit counter atomically.
    user_stmt = (
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
            User.first_seen_at,
            User.last_seen_at,
            User.visit_count,
        )
    )
    user_row = session.exec(user_stmt).one()

    # 2. Record this (phone, group_id) membership idempotently.
    group_stmt = (
        insert(UserGroup)
        .values(phone=payload.phone, group_id=payload.group_id, created_at=now)
        .on_conflict_do_nothing(index_elements=["phone", "group_id"])
    )
    session.exec(group_stmt)

    group_ids = _group_ids_for(session, payload.phone)
    session.commit()

    # visit_count only ever increments, so >1 reliably means a known number.
    return VisitCheckResponse(
        phone=payload.phone,
        is_returning=user_row.visit_count > 1,
        group_ids=group_ids,
        first_seen_at=_as_utc(user_row.first_seen_at),
        last_seen_at=_as_utc(user_row.last_seen_at),
        visit_count=user_row.visit_count,
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
        group_ids=_group_ids_for(session, phone),
        first_seen_at=_as_utc(user.first_seen_at),
        last_seen_at=_as_utc(user.last_seen_at),
        visit_count=user.visit_count,
    )
