"""Tests for the auth/setup endpoints — setup, login, logout, me, JWT auth."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SETUP_URL = "/api/auth/setup"
STATUS_URL = "/api/auth/setup-status"
LOGIN_URL = "/api/auth/login"
LOGOUT_URL = "/api/auth/logout"
ME_URL = "/api/auth/me"

VALID_PAYLOAD = {
    "username": "admin",
    "display_name": "Admin User",
    "password": "securepass123",
    "email": "admin@example.com",
}

LOGIN_CREDS = {"username": "admin", "password": "securepass123"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_and_login(client: TestClient) -> TestClient:
    """Create user via /setup and login, returning the same client (cookie set)."""
    client.post(SETUP_URL, json=VALID_PAYLOAD)
    resp = client.post(LOGIN_URL, json=LOGIN_CREDS)
    assert resp.status_code == 200
    return client


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
    resp = client.post(SETUP_URL, json=VALID_PAYLOAD)
    assert resp.status_code == 201
    assert "password_hash" not in resp.json()
    assert "password" not in resp.json()


def test_setup_without_email(client: TestClient):
    payload = {**VALID_PAYLOAD, "email": None}
    resp = client.post(SETUP_URL, json=payload)
    assert resp.status_code == 201
    assert resp.json()["email"] is None


# ---------------------------------------------------------------------------
# POST /setup — second call returns 409
# ---------------------------------------------------------------------------


def test_second_setup_returns_409(client: TestClient):
    resp1 = client.post(SETUP_URL, json=VALID_PAYLOAD)
    assert resp1.status_code == 201
    resp2 = client.post(SETUP_URL, json={"username": "other", "display_name": "Other", "password": "anothersecret"})
    assert resp2.status_code == 409


def test_setup_status_false_after_setup(client: TestClient):
    client.post(SETUP_URL, json=VALID_PAYLOAD)
    resp = client.get(STATUS_URL)
    assert resp.status_code == 200
    assert resp.json()["setup_required"] is False


# ---------------------------------------------------------------------------
# POST /setup — negative tests
# ---------------------------------------------------------------------------


def test_setup_missing_username_returns_422(client: TestClient):
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "username"}
    resp = client.post(SETUP_URL, json=payload)
    assert resp.status_code == 422


def test_setup_missing_display_name_returns_422(client: TestClient):
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "display_name"}
    resp = client.post(SETUP_URL, json=payload)
    assert resp.status_code == 422


def test_setup_missing_password_returns_422(client: TestClient):
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "password"}
    resp = client.post(SETUP_URL, json=payload)
    assert resp.status_code == 422


def test_setup_short_password_returns_400(client: TestClient):
    payload = {**VALID_PAYLOAD, "password": "short"}
    resp = client.post(SETUP_URL, json=payload)
    assert resp.status_code == 400


def test_setup_exactly_8_char_password_succeeds(client: TestClient):
    payload = {**VALID_PAYLOAD, "password": "12345678"}
    resp = client.post(SETUP_URL, json=payload)
    assert resp.status_code == 201


def test_setup_empty_body_returns_422(client: TestClient):
    resp = client.post(SETUP_URL, json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /login — happy path
# ---------------------------------------------------------------------------


def test_login_valid_credentials_returns_200(client: TestClient):
    """Valid login returns 200 and UserRead body."""
    client.post(SETUP_URL, json=VALID_PAYLOAD)
    resp = client.post(LOGIN_URL, json=LOGIN_CREDS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "admin"
    assert "password_hash" not in data
    assert "password" not in data


def test_login_sets_cookie(client: TestClient):
    """Successful login sets access_token cookie."""
    client.post(SETUP_URL, json=VALID_PAYLOAD)
    resp = client.post(LOGIN_URL, json=LOGIN_CREDS)
    assert resp.status_code == 200
    # TestClient stores cookies automatically; verify cookie is present in jar
    assert "access_token" in client.cookies


# ---------------------------------------------------------------------------
# POST /login — negative tests
# ---------------------------------------------------------------------------


def test_login_wrong_password_returns_401(client: TestClient):
    client.post(SETUP_URL, json=VALID_PAYLOAD)
    resp = client.post(LOGIN_URL, json={"username": "admin", "password": "wrongpass"})
    assert resp.status_code == 401


def test_login_nonexistent_user_returns_401(client: TestClient):
    client.post(SETUP_URL, json=VALID_PAYLOAD)
    resp = client.post(LOGIN_URL, json={"username": "nobody", "password": "doesntmatter"})
    assert resp.status_code == 401


def test_login_inactive_user_returns_401(client: TestClient, db):
    """An inactive user cannot log in."""
    client.post(SETUP_URL, json=VALID_PAYLOAD)
    # Mark user inactive directly in DB
    from app.models import User
    user = db.query(User).filter(User.username == "admin").first()
    user.is_active = False
    db.commit()
    resp = client.post(LOGIN_URL, json=LOGIN_CREDS)
    assert resp.status_code == 401


def test_login_missing_username_returns_422(client: TestClient):
    resp = client.post(LOGIN_URL, json={"password": "pass"})
    assert resp.status_code == 422


def test_login_missing_password_returns_422(client: TestClient):
    resp = client.post(LOGIN_URL, json={"username": "admin"})
    assert resp.status_code == 422


def test_login_empty_body_returns_422(client: TestClient):
    resp = client.post(LOGIN_URL, json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /me — happy path
# ---------------------------------------------------------------------------


def test_me_with_valid_cookie_returns_200(client: TestClient):
    _setup_and_login(client)
    resp = client.get(ME_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "admin"
    assert "password_hash" not in data


# ---------------------------------------------------------------------------
# GET /me — unauthenticated / error paths
# ---------------------------------------------------------------------------


def test_me_without_cookie_returns_401(client: TestClient):
    resp = client.get(ME_URL)
    assert resp.status_code == 401


def test_me_with_invalid_token_returns_401(client: TestClient):
    client.cookies.set("access_token", "not.a.valid.token")
    resp = client.get(ME_URL)
    assert resp.status_code == 401


def test_me_with_expired_token_returns_401(client: TestClient):
    """Manually craft an expired JWT — /me must reject with 401."""
    client.post(SETUP_URL, json=VALID_PAYLOAD)
    # Build expired token
    from app.config import settings
    exp = datetime.now(UTC) - timedelta(seconds=1)
    token = jwt.encode({"sub": "1", "exp": exp}, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    client.cookies.set("access_token", token)
    resp = client.get(ME_URL)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "token_expired"


def test_me_with_tampered_token_returns_401(client: TestClient):
    """JWT signed with wrong key → 401."""
    client.post(SETUP_URL, json=VALID_PAYLOAD)
    token = jwt.encode({"sub": "1"}, "wrong-secret-key", algorithm="HS256")
    client.cookies.set("access_token", token)
    resp = client.get(ME_URL)
    assert resp.status_code == 401


def test_me_after_user_deleted_returns_401(client: TestClient, db):
    """Valid JWT but user no longer exists → 401."""
    _setup_and_login(client)
    # Delete the user directly
    from app.models import User
    db.query(User).delete()
    db.commit()
    resp = client.get(ME_URL)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /logout
# ---------------------------------------------------------------------------


def test_logout_returns_200(client: TestClient):
    _setup_and_login(client)
    resp = client.post(LOGOUT_URL)
    assert resp.status_code == 200


def test_logout_clears_cookie(client: TestClient):
    _setup_and_login(client)
    client.post(LOGOUT_URL)
    # After logout the cookie jar should be empty or token cleared
    # TestClient's cookie jar reflects Set-Cookie header; empty value + max_age=0 deletes it
    token = client.cookies.get("access_token")
    assert not token  # either absent or empty string


def test_me_after_logout_returns_401(client: TestClient):
    _setup_and_login(client)
    client.post(LOGOUT_URL)
    resp = client.get(ME_URL)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Protected route integration tests (T02)
# ---------------------------------------------------------------------------

STREAMS_URL = "/api/streams/"
STATISTICS_URL = "/api/statistics/summary"
HEALTH_URL = "/api/health"


def test_streams_without_cookie_returns_401(client: TestClient):
    resp = client.get(STREAMS_URL)
    assert resp.status_code == 401


def test_statistics_without_cookie_returns_401(client: TestClient):
    resp = client.get(STATISTICS_URL)
    assert resp.status_code == 401


def test_setup_status_without_cookie_returns_200(client: TestClient):
    resp = client.get(STATUS_URL)
    assert resp.status_code == 200


def test_health_without_cookie_returns_200(client: TestClient):
    resp = client.get(HEALTH_URL)
    assert resp.status_code == 200


def test_streams_with_valid_cookie_returns_200(client: TestClient):
    _setup_and_login(client)
    resp = client.get(STREAMS_URL)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# OIDC endpoint tests
# ---------------------------------------------------------------------------

OIDC_CONFIG_URL = "/api/auth/oidc/config"
OIDC_LOGIN_URL = "/api/auth/oidc/login"
OIDC_CALLBACK_URL = "/api/auth/oidc/callback"

VALID_OIDC_CONFIG = {
    "issuer_url": "https://accounts.example.com",
    "client_id": "test-client-id",
    "client_secret": "test-client-secret",
    "provider_name": "Example IdP",
}


# --- GET /oidc/config ---


def test_oidc_config_returns_disabled_when_not_configured(client: TestClient):
    """GET /oidc/config returns enabled=False when no OIDC settings exist."""
    resp = client.get(OIDC_CONFIG_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False


def test_oidc_config_no_auth_required(client: TestClient):
    """GET /oidc/config is public — no cookie needed."""
    resp = client.get(OIDC_CONFIG_URL)
    assert resp.status_code == 200


# --- PUT /oidc/config ---


def test_put_oidc_config_requires_admin(client: TestClient):
    """PUT /oidc/config with no auth returns 401."""
    resp = client.put(OIDC_CONFIG_URL, json=VALID_OIDC_CONFIG)
    assert resp.status_code == 401


def test_put_oidc_config_missing_issuer_url_returns_422(client: TestClient):
    """Empty issuer_url → 422 validation error."""
    _setup_and_login(client)
    payload = {k: v for k, v in VALID_OIDC_CONFIG.items() if k != "issuer_url"}
    resp = client.put(OIDC_CONFIG_URL, json=payload)
    assert resp.status_code == 422


def test_put_oidc_config_missing_client_id_returns_422(client: TestClient):
    """Missing client_id → 422 validation error."""
    _setup_and_login(client)
    payload = {k: v for k, v in VALID_OIDC_CONFIG.items() if k != "client_id"}
    resp = client.put(OIDC_CONFIG_URL, json=payload)
    assert resp.status_code == 422


def test_put_oidc_config_saves_and_returns_enabled(client: TestClient):
    """Admin can save OIDC config and GET returns enabled=True."""
    _setup_and_login(client)
    resp = client.put(OIDC_CONFIG_URL, json=VALID_OIDC_CONFIG)
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["issuer_url"] == VALID_OIDC_CONFIG["issuer_url"]

    # Verify GET now returns enabled
    get_resp = client.get(OIDC_CONFIG_URL)
    assert get_resp.status_code == 200
    assert get_resp.json()["enabled"] is True


# --- GET /oidc/login ---


def test_oidc_login_returns_400_when_not_configured(client: TestClient):
    """GET /oidc/login returns 400 when OIDC is not configured."""
    resp = client.get(OIDC_LOGIN_URL, follow_redirects=False)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "oidc_not_configured"


# --- GET /oidc/callback ---


def test_oidc_callback_returns_401_when_not_configured(client: TestClient):
    """GET /oidc/callback with no OIDC config returns 401."""
    resp = client.get(OIDC_CALLBACK_URL + "?code=fake&state=fake", follow_redirects=False)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "oidc_callback_failed"


def test_oidc_callback_token_exchange_failure_returns_401(client: TestClient):
    """When Authlib authorize_access_token raises, callback returns 401."""
    _setup_and_login(client)
    client.put(OIDC_CONFIG_URL, json=VALID_OIDC_CONFIG)

    # Patch authorize_access_token to raise
    from unittest.mock import AsyncMock, patch
    with patch(
        "authlib.integrations.starlette_client.StarletteOAuth2App.authorize_access_token",
        new_callable=AsyncMock,
        side_effect=Exception("provider error"),
    ):
        resp = client.get(
            OIDC_CALLBACK_URL + "?code=badcode&state=badstate",
            follow_redirects=False,
        )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "oidc_callback_failed"
