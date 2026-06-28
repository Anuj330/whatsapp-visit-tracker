"""Tests for the visit-tracking API."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app


@pytest.fixture(name="client")
def client_fixture():
    """Provide a TestClient backed by a fresh in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def get_session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_session_override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_first_visit_is_not_returning(client):
    """A first visit returns is_returning=false, visit_count=1."""
    resp = client.post(
        "/visits/check", json={"phone": "+1 555 0100", "group_id": "g1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["phone"] == "+15550100"
    assert body["group_id"] == "g1"
    assert body["phone_group_id"] == "+15550100_g1"
    assert body["is_returning"] is False
    assert body["visit_count"] == 1
    assert body["first_seen_at"] == body["last_seen_at"]


def test_second_visit_is_returning(client):
    """A second call for the same phone+group returns is_returning=true."""
    client.post("/visits/check", json={"phone": "15550100", "group_id": "g1"})
    resp = client.post(
        "/visits/check", json={"phone": "15550100", "group_id": "g1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_returning"] is True
    assert body["visit_count"] == 2
    assert body["last_seen_at"] >= body["first_seen_at"]


def test_same_phone_different_group_is_separate(client):
    """The same phone in a different group is tracked independently."""
    client.post("/visits/check", json={"phone": "15550100", "group_id": "g1"})
    resp = client.post(
        "/visits/check", json={"phone": "15550100", "group_id": "g2"}
    )
    body = resp.json()
    assert body["phone_group_id"] == "15550100_g2"
    assert body["is_returning"] is False
    assert body["visit_count"] == 1


def test_get_user_found_and_not_found(client):
    """GET /users/{phone_group_id} returns the record, or 404 when absent."""
    assert client.get("/users/19999999_g1").status_code == 404
    client.post("/visits/check", json={"phone": "19999999", "group_id": "g1"})
    resp = client.get("/users/19999999_g1")
    assert resp.status_code == 200
    assert resp.json()["visit_count"] == 1


def test_invalid_input_returns_422(client):
    """Empty/missing phone or group_id is rejected with 422."""
    assert (
        client.post(
            "/visits/check", json={"phone": "   ", "group_id": "g1"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/visits/check", json={"phone": "15550100", "group_id": ""}
        ).status_code
        == 422
    )
    assert (
        client.post("/visits/check", json={"phone": "15550100"}).status_code
        == 422
    )


def test_health(client):
    """Health endpoint reports ok."""
    assert client.get("/health").json() == {"status": "ok"}
