"""Database and API schema models."""

from datetime import datetime

from pydantic import BaseModel, field_validator
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """A WhatsApp user tracked by their wa_id / phone number."""

    __tablename__ = "users"

    phone: str = Field(primary_key=True)
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


class VisitCheckRequest(BaseModel):
    """Request body for POST /visits/check."""

    phone: str

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, value: object) -> str:
        """Validate and normalize the incoming phone number."""
        return _normalize_phone(value)


class UserResponse(BaseModel):
    """Stored user record, returned by GET /users/{phone}."""

    phone: str
    first_seen_at: datetime
    last_seen_at: datetime
    visit_count: int


class VisitCheckResponse(BaseModel):
    """Response body for POST /visits/check."""

    phone: str
    is_returning: bool
    first_seen_at: datetime
    last_seen_at: datetime
    visit_count: int
