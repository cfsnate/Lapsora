"""Tests for the auth/setup endpoints."""

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SETUP_URL = "/api/auth/setup"
STATUS_URL = "/api/auth/setup-status"

VALID_PAYLOAD = {
    "username": "admin",
    "display_name": "Admin User",
    "password": "securepass123",
    "email": "admin@example.com",
}


# ---------------------------------------------------------------------------
# Setup-status
# ---------------------------------------------------------------------------


def test_setup_status_returns_true_on_empty_db(client: TestClient):
    """Fresh DB → setup_required must be True."""
    resp = client.get(STATUS_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data["setup_required"] is True


def test_setup_status_is_idempotent(client: TestClient):
    """Calling GET /setup-status multiple times is safe and consistent."""
    for _ in range(3):
        resp = client.get(STATUS_URL)
        assert resp.status_code == 200
        assert resp.json()["setup_required"] is True


# ---------------------------------------------------------------------------
# POST /setup — happy path
# ---------------------------------------------------------------------------


def test_setup_creates_admin_user(client: TestClient):
    """POST /setup on empty DB creates admin and returns UserRead."""
    resp = client.post(SETUP_URL, json=VALID_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "admin"
    assert data["display_name"] == "Admin User"
    assert data["email"] == "admin@example.com"
    assert data["role"] == "admin"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_setup_response_excludes_password_hash(client: TestClient):
    """password_hash must never appear in the API response."""
    resp = client.post(SETUP_URL, json=VALID_PAYLOAD)
    assert resp.status_code == 201
    assert "password_hash" not in resp.json()
    assert "password" not in resp.json()


def test_setup_without_email(client: TestClient):
    """Email is optional — omitting it should still succeed."""
    payload = {**VALID_PAYLOAD, "email": None}
    resp = client.post(SETUP_URL, json=payload)
    assert resp.status_code == 201
    assert resp.json()["email"] is None


# ---------------------------------------------------------------------------
# POST /setup — second call returns 409
# ---------------------------------------------------------------------------


def test_second_setup_returns_409(client: TestClient):
    """Second POST /setup must return 409 Conflict."""
    resp1 = client.post(SETUP_URL, json=VALID_PAYLOAD)
    assert resp1.status_code == 201

    resp2 = client.post(SETUP_URL, json={"username": "other", "display_name": "Other", "password": "anothersecret"})
    assert resp2.status_code == 409


def test_setup_status_false_after_setup(client: TestClient):
    """After setup completes, setup_required must be False."""
    client.post(SETUP_URL, json=VALID_PAYLOAD)
    resp = client.get(STATUS_URL)
    assert resp.status_code == 200
    assert resp.json()["setup_required"] is False


# ---------------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------------


def test_setup_missing_username_returns_422(client: TestClient):
    """Missing required field 'username' → 422 Unprocessable Entity."""
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "username"}
    resp = client.post(SETUP_URL, json=payload)
    assert resp.status_code == 422


def test_setup_missing_display_name_returns_422(client: TestClient):
    """Missing required field 'display_name' → 422."""
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "display_name"}
    resp = client.post(SETUP_URL, json=payload)
    assert resp.status_code == 422


def test_setup_missing_password_returns_422(client: TestClient):
    """Missing required field 'password' → 422."""
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "password"}
    resp = client.post(SETUP_URL, json=payload)
    assert resp.status_code == 422


def test_setup_short_password_returns_400(client: TestClient):
    """Password shorter than 8 chars → 400 Bad Request."""
    payload = {**VALID_PAYLOAD, "password": "short"}
    resp = client.post(SETUP_URL, json=payload)
    assert resp.status_code == 400


def test_setup_exactly_8_char_password_succeeds(client: TestClient):
    """Exactly 8-char password is at the boundary — should succeed."""
    payload = {**VALID_PAYLOAD, "password": "12345678"}
    resp = client.post(SETUP_URL, json=payload)
    assert resp.status_code == 201


def test_setup_empty_body_returns_422(client: TestClient):
    """Empty POST body → 422."""
    resp = client.post(SETUP_URL, json={})
    assert resp.status_code == 422
