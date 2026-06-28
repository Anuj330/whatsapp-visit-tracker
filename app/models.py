"""Database and API schema models."""

from datetime import datetime

from pydantic import BaseModel, field_validator
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """A WhatsApp user, keyed by phone number.

    One row per phone. The groups (regions) a phone belongs to are tracked in
    the ``user_groups`` table, so a single number can map to many group_ids.
    """

    __tablename__ = "users"

    phone: str = Field(primary_key=True)
    first_seen_at: datetime
    last_seen_at: datetime
    visit_count: int


class UserGroup(SQLModel, table=True):
    """Membership of a phone in a group (region).

    Composite primary key (phone, group_id) makes each membership unique, so
    re-sending the same pair is idempotent.
    """

    __tablename__ = "user_groups"

    phone: str = Field(primary_key=True)
    group_id: str = Field(primary_key=True)
    created_at: datetime


def _normalize_phone(value: object) -> str:
    """Strip whitespace and collapse to a single leading '+' if present.

    Raises ValueError on anything that isn't a non-empty string, which
    FastAPI surfaces as a 422 response.
    """
    if not isinstance(value, str):
        raise ValueError("phone must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("phone must be a non-empty string")
    # Keep at most one leading '+', drop any internal whitespace.
    has_plus = cleaned.startswith("+")
    digits = "".join(cleaned.replace("+", "").split())
    if not digits:
        raise ValueError("phone must contain at least one non-'+' character")
    return ("+" + digits) if has_plus else digits


def _normalize_group_id(value: object) -> str:
    """Validate group_id as a non-empty string and strip surrounding space."""
    if not isinstance(value, str):
        raise ValueError("group_id must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("group_id must be a non-empty string")
    return cleaned


class VisitCheckRequest(BaseModel):
    """Request body for POST /visits/check."""

    phone: str
    group_id: str

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, value: object) -> str:
        """Validate and normalize the incoming phone number."""
        return _normalize_phone(value)

    @field_validator("group_id", mode="before")
    @classmethod
    def validate_group_id(cls, value: object) -> str:
        """Validate and normalize the incoming group id."""
        return _normalize_group_id(value)


class UserResponse(BaseModel):
    """Stored user record, returned by GET /users/{phone}."""

    phone: str
    group_ids: list[str]
    first_seen_at: datetime
    last_seen_at: datetime
    visit_count: int


class VisitCheckResponse(BaseModel):
    """Response body for POST /visits/check.

    ``is_returning`` is false for a brand-new number and true if the phone was
    already in the database. ``group_ids`` lists every group (region) the
    number is currently saved to, including the one from this request.
    """

    phone: str
    is_returning: bool
    group_ids: list[str]
    first_seen_at: datetime
    last_seen_at: datetime
    visit_count: int
