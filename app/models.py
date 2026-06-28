"""Database and API schema models."""

from datetime import datetime

from pydantic import BaseModel, field_validator
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """A WhatsApp user tracked per group.

    The primary key ``phone_group_id`` is ``"{phone}_{group_id}"``, so the same
    phone number is counted separately in each group it appears in.
    """

    __tablename__ = "users"

    phone_group_id: str = Field(primary_key=True)
    phone: str
    group_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    visit_count: int


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


def make_phone_group_id(phone: str, group_id: str) -> str:
    """Build the composite primary key from a phone and group id."""
    return f"{phone}_{group_id}"


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
    """Stored user record, returned by GET /users/{phone_group_id}."""

    phone_group_id: str
    phone: str
    group_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    visit_count: int


class VisitCheckResponse(BaseModel):
    """Response body for POST /visits/check."""

    phone_group_id: str
    phone: str
    group_id: str
    is_returning: bool
    first_seen_at: datetime
    last_seen_at: datetime
    visit_count: int
