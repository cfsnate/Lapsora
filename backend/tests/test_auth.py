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


def test_put_oidc_config_without_secret_succeeds(client: TestClient):
    """Admin can save OIDC config without client_secret (public client / PKCE)."""
    _setup_and_login(client)
    payload = {
        "issuer_url": "https://okta.example.com",
        "client_id": "public-client-id",
        "provider_name": "Okta",
    }
    resp = client.put(OIDC_CONFIG_URL, json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["issuer_url"] == "https://okta.example.com"


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


# ---------------------------------------------------------------------------
# RBAC helpers
# ---------------------------------------------------------------------------

USERS_URL = "/api/auth/users"


def _admin_setup_and_login(client: TestClient) -> int:
    """Create admin via /setup and return admin_id (client cookie is set)."""
    resp = client.post(SETUP_URL, json=VALID_PAYLOAD)
    assert resp.status_code == 201
    admin_id = resp.json()["id"]
    login_resp = client.post(LOGIN_URL, json=LOGIN_CREDS)
    assert login_resp.status_code == 200
    return admin_id


def _create_user(client: TestClient, username: str = "testuser", role: str = "user"):
    """Admin creates a new user and returns the raw response."""
    return client.post(
        USERS_URL,
        json={"username": username, "display_name": "Test User", "password": "pass1234", "role": role},
    )


def _make_stream_and_profiles(db, count: int = 2):
    """Create a Stream and `count` Profiles in the test DB. Returns (stream, profiles)."""
    from app.models import Profile, Stream
    stream = Stream(name="Test Stream", url="rtsp://localhost/test")
    db.add(stream)
    db.flush()
    profiles = []
    for i in range(count):
        p = Profile(stream_id=stream.id, name=f"Profile {i+1}", interval_seconds=60)
        db.add(p)
        profiles.append(p)
    db.flush()
    return stream, profiles


# ---------------------------------------------------------------------------
# RBAC-01: Admin User Management
# ---------------------------------------------------------------------------


def test_admin_create_user(client: TestClient):
    """Admin creates a user with role='user' -> 201 with correct fields."""
    _admin_setup_and_login(client)
    resp = _create_user(client, username="newuser")
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "newuser"
    assert data["role"] == "user"
    assert data["is_active"] is True
    assert "id" in data
    assert "accessible_profile_ids" in data
    assert "password_hash" not in data


def test_admin_create_user_duplicate_username(client: TestClient):
    """Creating a user with an existing username returns 409."""
    _admin_setup_and_login(client)
    _create_user(client, username="dupuser")
    resp = _create_user(client, username="dupuser")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "username_taken"


def test_admin_list_users(client: TestClient):
    """Admin GET /users returns all users including newly created ones."""
    _admin_setup_and_login(client)
    _create_user(client, username="user_a")
    _create_user(client, username="user_b")
    resp = client.get(USERS_URL)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    usernames = {u["username"] for u in data}
    assert "admin" in usernames
    assert "user_a" in usernames
    assert "user_b" in usernames


def test_admin_get_user(client: TestClient):
    """Admin GET /users/{id} returns the user's details."""
    _admin_setup_and_login(client)
    user_id = _create_user(client, username="fetchme").json()["id"]
    resp = client.get(f"{USERS_URL}/{user_id}")
    assert resp.status_code == 200
    assert resp.json()["username"] == "fetchme"


def test_admin_update_user(client: TestClient):
    """Admin PUT /users/{id} with new display_name -> 200, field updated."""
    _admin_setup_and_login(client)
    user_id = _create_user(client, username="updateme").json()["id"]
    resp = client.put(f"{USERS_URL}/{user_id}", json={"display_name": "Updated Name"})
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Updated Name"


def test_admin_update_user_password(client: TestClient):
    """Admin changes a user password; user can log in with new password."""
    _admin_setup_and_login(client)
    _create_user(client, username="pwduser")
    all_users = client.get(USERS_URL).json()
    user_id = next(u["id"] for u in all_users if u["username"] == "pwduser")

    resp = client.put(f"{USERS_URL}/{user_id}", json={"password": "newpass99"})
    assert resp.status_code == 200

    # Logout admin, login as pwduser with new password
    client.post(LOGOUT_URL)
    login_resp = client.post(LOGIN_URL, json={"username": "pwduser", "password": "newpass99"})
    assert login_resp.status_code == 200


def test_admin_disable_user(client: TestClient):
    """Admin DELETE /users/{id} sets is_active=False and returns updated user."""
    _admin_setup_and_login(client)
    user_id = _create_user(client, username="disableme").json()["id"]
    resp = client.delete(f"{USERS_URL}/{user_id}")
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_admin_cannot_disable_self(client: TestClient):
    """Admin cannot disable themselves -> 400."""
    admin_id = _admin_setup_and_login(client)
    resp = client.delete(f"{USERS_URL}/{admin_id}")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "cannot_disable_self"


def test_nonadmin_cannot_access_user_management(client: TestClient):
    """Non-admin user calls GET /users -> 403."""
    _admin_setup_and_login(client)
    _create_user(client, username="regular", role="user")
    client.post(LOGOUT_URL)
    client.post(LOGIN_URL, json={"username": "regular", "password": "pass1234"})
    resp = client.get(USERS_URL)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# RBAC-02: Profile Access
# ---------------------------------------------------------------------------


def test_admin_set_profile_access(client: TestClient, db):
    """Admin PUT /users/{id}/profiles sets profile access -> 200."""
    _admin_setup_and_login(client)
    user_id = _create_user(client, username="profuser").json()["id"]
    _, profiles = _make_stream_and_profiles(db, count=2)
    db.commit()

    resp = client.put(
        f"{USERS_URL}/{user_id}/profiles",
        json={"profile_ids": [profiles[0].id, profiles[1].id]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["profile_ids"]) == {profiles[0].id, profiles[1].id}


def test_admin_get_profile_access(client: TestClient, db):
    """Admin GET /users/{id}/profiles returns the set profile IDs."""
    _admin_setup_and_login(client)
    user_id = _create_user(client, username="profuser2").json()["id"]
    _, profiles = _make_stream_and_profiles(db, count=3)
    db.commit()

    client.put(f"{USERS_URL}/{user_id}/profiles", json={"profile_ids": [profiles[0].id]})
    resp = client.get(f"{USERS_URL}/{user_id}/profiles")
    assert resp.status_code == 200
    assert resp.json()["profile_ids"] == [profiles[0].id]


def test_nonadmin_sees_only_permitted_profiles(client: TestClient, db):
    """Non-admin sees only the profiles they have access to in list endpoint."""
    _admin_setup_and_login(client)
    user_id = _create_user(client, username="limiteduser").json()["id"]
    stream, profiles = _make_stream_and_profiles(db, count=2)
    db.commit()

    client.put(f"{USERS_URL}/{user_id}/profiles", json={"profile_ids": [profiles[0].id]})

    client.post(LOGOUT_URL)
    client.post(LOGIN_URL, json={"username": "limiteduser", "password": "pass1234"})

    resp = client.get(f"/api/streams/{stream.id}/profiles")
    assert resp.status_code == 200
    returned_ids = [p["id"] for p in resp.json()]
    assert profiles[0].id in returned_ids
    assert profiles[1].id not in returned_ids


def test_nonadmin_denied_unpermitted_profile(client: TestClient, db):
    """Non-admin GET /profiles/{unpermitted_id} -> 403."""
    _admin_setup_and_login(client)
    user_id = _create_user(client, username="limiteduser2").json()["id"]
    _, profiles = _make_stream_and_profiles(db, count=2)
    db.commit()

    client.put(f"{USERS_URL}/{user_id}/profiles", json={"profile_ids": [profiles[0].id]})

    client.post(LOGOUT_URL)
    client.post(LOGIN_URL, json={"username": "limiteduser2", "password": "pass1234"})

    resp = client.get(f"/api/profiles/{profiles[1].id}")
    assert resp.status_code == 403


def test_nonadmin_can_access_permitted_profile(client: TestClient, db):
    """Non-admin GET /profiles/{permitted_id} -> 200."""
    _admin_setup_and_login(client)
    user_id = _create_user(client, username="permitteduser").json()["id"]
    _, profiles = _make_stream_and_profiles(db, count=2)
    db.commit()

    client.put(f"{USERS_URL}/{user_id}/profiles", json={"profile_ids": [profiles[0].id]})

    client.post(LOGOUT_URL)
    client.post(LOGIN_URL, json={"username": "permitteduser", "password": "pass1234"})

    resp = client.get(f"/api/profiles/{profiles[0].id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == profiles[0].id


def test_admin_sees_all_profiles(client: TestClient, db):
    """Admin GET /streams/{id}/profiles returns all profiles regardless of access grants."""
    _admin_setup_and_login(client)
    stream, profiles = _make_stream_and_profiles(db, count=3)
    db.commit()

    resp = client.get(f"/api/streams/{stream.id}/profiles")
    assert resp.status_code == 200
    returned_ids = {p["id"] for p in resp.json()}
    for p in profiles:
        assert p.id in returned_ids


def test_set_profile_access_invalid_profile(client: TestClient):
    """PUT /users/{id}/profiles with non-existent profile_id -> 400."""
    _admin_setup_and_login(client)
    user_id = _create_user(client, username="accesstest").json()["id"]
    resp = client.put(f"{USERS_URL}/{user_id}/profiles", json={"profile_ids": [99999]})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Cascade behavior tests
# ---------------------------------------------------------------------------


def test_user_deletion_cascades_access(client: TestClient, db):
    """Deleting a user removes their UserProfileAccess rows."""
    from app.models import User, UserProfileAccess

    _admin_setup_and_login(client)
    user_id = _create_user(client, username="cascadeuser").json()["id"]
    _, profiles = _make_stream_and_profiles(db, count=2)
    db.commit()

    client.put(f"{USERS_URL}/{user_id}/profiles", json={"profile_ids": [profiles[0].id]})

    rows_before = db.query(UserProfileAccess).filter(UserProfileAccess.user_id == user_id).all()
    assert len(rows_before) == 1

    user = db.query(User).filter(User.id == user_id).first()
    db.delete(user)
    db.commit()

    rows_after = db.query(UserProfileAccess).filter(UserProfileAccess.user_id == user_id).all()
    assert len(rows_after) == 0


def test_profile_deletion_cascades_access(client: TestClient, db):
    """Deleting a profile removes associated UserProfileAccess rows."""
    from app.models import Profile, UserProfileAccess

    _admin_setup_and_login(client)
    user_id = _create_user(client, username="profdel").json()["id"]
    _, profiles = _make_stream_and_profiles(db, count=1)
    db.commit()

    client.put(f"{USERS_URL}/{user_id}/profiles", json={"profile_ids": [profiles[0].id]})

    rows_before = db.query(UserProfileAccess).filter(UserProfileAccess.profile_id == profiles[0].id).all()
    assert len(rows_before) == 1

    profile = db.query(Profile).filter(Profile.id == profiles[0].id).first()
    db.delete(profile)
    db.commit()

    rows_after = db.query(UserProfileAccess).filter(UserProfileAccess.profile_id == profiles[0].id).all()
    assert len(rows_after) == 0


# ---------------------------------------------------------------------------
# PUT /auth/me — self-update tests
# ---------------------------------------------------------------------------

PUT_ME_URL = "/api/auth/me"


def test_update_me_display_name(client: TestClient):
    """Authenticated user can update their own display_name."""
    _setup_and_login(client)
    resp = client.put(PUT_ME_URL, json={"display_name": "New Display Name"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "New Display Name"


def test_update_me_password_and_login(client: TestClient):
    """Authenticated user can change their own password and then login with the new one."""
    _setup_and_login(client)
    resp = client.put(PUT_ME_URL, json={"password": "newpassword456"})
    assert resp.status_code == 200

    # Logout then try new password
    client.post(LOGOUT_URL)
    login_resp = client.post(LOGIN_URL, json={"username": "admin", "password": "newpassword456"})
    assert login_resp.status_code == 200


def test_update_me_unauthenticated(client: TestClient):
    """Unauthenticated PUT /me -> 401."""
    resp = client.put(PUT_ME_URL, json={"display_name": "Hacker"})
    assert resp.status_code == 401


def test_update_me_no_role_field(client: TestClient):
    """SelfUpdate schema has no role field — sending role in payload has no effect."""
    _setup_and_login(client)
    # role is not in SelfUpdate schema; it should be ignored (FastAPI ignores extra fields)
    resp = client.put(PUT_ME_URL, json={"display_name": "Safe", "role": "superadmin"})
    assert resp.status_code == 200
    # Role must remain unchanged
    me_resp = client.get(ME_URL)
    assert me_resp.json()["role"] == "admin"


# ---------------------------------------------------------------------------
# Group CRUD tests
# ---------------------------------------------------------------------------

GROUPS_URL = "/api/auth/groups"


def test_list_groups_empty(client: TestClient):
    """Admin listing groups on empty DB returns []."""
    _setup_and_login(client)
    resp = client.get(GROUPS_URL)
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_group_basic(client: TestClient):
    """Admin can create a group with name and role."""
    _setup_and_login(client)
    resp = client.post(GROUPS_URL, json={"name": "viewers", "role": "user"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "viewers"
    assert data["role"] == "user"
    assert data["profile_ids"] == []
    assert data["oidc_group_names"] == []


def test_create_group_with_profiles_and_mappings(client: TestClient, db):
    """Admin can create a group with profile access and OIDC mappings."""
    _setup_and_login(client)
    _, profiles = _make_stream_and_profiles(db, count=2)
    resp = client.post(GROUPS_URL, json={
        "name": "operators",
        "role": "admin",
        "profile_ids": [profiles[0].id, profiles[1].id],
        "oidc_group_names": ["oidc-operators", "ops-team"],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["role"] == "admin"
    assert set(data["profile_ids"]) == {profiles[0].id, profiles[1].id}
    assert set(data["oidc_group_names"]) == {"oidc-operators", "ops-team"}


def test_create_group_duplicate_name(client: TestClient):
    """Creating a group with a duplicate name returns 409."""
    _setup_and_login(client)
    client.post(GROUPS_URL, json={"name": "dup"})
    resp = client.post(GROUPS_URL, json={"name": "dup"})
    assert resp.status_code == 409
    assert "group_name_taken" in resp.json()["detail"]


def test_create_group_oidc_name_conflict(client: TestClient):
    """Creating a group reusing an OIDC group name already mapped elsewhere returns 409."""
    _setup_and_login(client)
    client.post(GROUPS_URL, json={"name": "g1", "oidc_group_names": ["shared-name"]})
    resp = client.post(GROUPS_URL, json={"name": "g2", "oidc_group_names": ["shared-name"]})
    assert resp.status_code == 409
    assert "oidc_group_names_taken" in resp.json()["detail"]


def test_create_group_non_admin_rejected(client: TestClient, db):
    """Non-admin user cannot create groups -> 403."""
    _setup_and_login(client)
    client.post(f"{USERS_URL}", json={
        "username": "viewer", "display_name": "V", "password": "viewerpass1", "role": "user"
    })
    client.post(LOGOUT_URL)
    client.post(LOGIN_URL, json={"username": "viewer", "password": "viewerpass1"})
    resp = client.post(GROUPS_URL, json={"name": "nope"})
    assert resp.status_code == 403


def test_update_group_name_and_role(client: TestClient):
    """Admin can update group name and role."""
    _setup_and_login(client)
    resp = client.post(GROUPS_URL, json={"name": "old", "role": "user"})
    gid = resp.json()["id"]
    resp = client.put(f"{GROUPS_URL}/{gid}", json={"name": "new", "role": "admin"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "new"
    assert resp.json()["role"] == "admin"


def test_update_group_profiles_and_mappings(client: TestClient, db):
    """Admin can replace a group's profiles and OIDC mappings."""
    _setup_and_login(client)
    _, profiles = _make_stream_and_profiles(db, count=3)
    resp = client.post(GROUPS_URL, json={
        "name": "g", "profile_ids": [profiles[0].id], "oidc_group_names": ["old-mapping"],
    })
    gid = resp.json()["id"]

    resp = client.put(f"{GROUPS_URL}/{gid}", json={
        "profile_ids": [profiles[1].id, profiles[2].id],
        "oidc_group_names": ["new-mapping"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert set(data["profile_ids"]) == {profiles[1].id, profiles[2].id}
    assert data["oidc_group_names"] == ["new-mapping"]


def test_delete_group(client: TestClient):
    """Admin can delete a group."""
    _setup_and_login(client)
    resp = client.post(GROUPS_URL, json={"name": "to-delete"})
    gid = resp.json()["id"]
    resp = client.delete(f"{GROUPS_URL}/{gid}")
    assert resp.status_code == 204

    # Confirm it's gone
    resp = client.get(GROUPS_URL)
    assert all(g["id"] != gid for g in resp.json())


def test_delete_group_not_found(client: TestClient):
    """Deleting a non-existent group returns 404."""
    _setup_and_login(client)
    resp = client.delete(f"{GROUPS_URL}/9999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# OIDC Group Sync tests
# ---------------------------------------------------------------------------


def test_oidc_group_sync_sets_role_and_profiles(client: TestClient, db):
    """OIDC callback with matching groups syncs user role and profile access."""
    from unittest.mock import AsyncMock, patch
    from app.models import Group, GroupProfileAccess, OIDCGroupMapping, Setting, User, UserProfileAccess
    from app.config import encrypt

    _setup_and_login(client)

    # Create a stream with profiles
    _, profiles = _make_stream_and_profiles(db, count=3)

    # Create a group with admin role and profiles[0,1]
    group = Group(name="admins", role="admin")
    db.add(group)
    db.flush()
    db.add(GroupProfileAccess(group_id=group.id, profile_id=profiles[0].id))
    db.add(GroupProfileAccess(group_id=group.id, profile_id=profiles[1].id))
    db.add(OIDCGroupMapping(group_id=group.id, oidc_group_name="idp-admins"))

    # Setup OIDC config
    db.add(Setting(key="oidc_issuer_url", value="https://idp.example.com"))
    db.add(Setting(key="oidc_client_id", value="test-client"))
    db.add(Setting(key="oidc_client_secret", value=encrypt("secret")))
    db.commit()

    # Mock the OIDC flow and call the internal sync function directly
    from app.routers.auth import _sync_user_groups

    # Create a test OIDC user
    oidc_user = User(
        username="oidcuser",
        display_name="OIDC User",
        password_hash="!",
        role="user",
        oidc_provider="oidc",
        oidc_subject="sub123",
    )
    db.add(oidc_user)
    db.commit()
    db.refresh(oidc_user)

    # Simulate userinfo with groups claim
    userinfo = {"sub": "sub123", "groups": ["idp-admins", "some-other-group"]}
    _sync_user_groups(db, oidc_user, userinfo)
    db.refresh(oidc_user)

    assert oidc_user.role == "admin"
    access = db.query(UserProfileAccess).filter(UserProfileAccess.user_id == oidc_user.id).all()
    assert set(r.profile_id for r in access) == {profiles[0].id, profiles[1].id}


def test_oidc_group_sync_union_of_multiple_groups(client: TestClient, db):
    """User matching multiple groups gets the union of all profile sets."""
    from app.models import Group, GroupProfileAccess, OIDCGroupMapping, User, UserProfileAccess
    from app.routers.auth import _sync_user_groups

    _setup_and_login(client)
    _, profiles = _make_stream_and_profiles(db, count=3)

    g1 = Group(name="g1", role="user")
    g2 = Group(name="g2", role="user")
    db.add_all([g1, g2])
    db.flush()
    db.add(GroupProfileAccess(group_id=g1.id, profile_id=profiles[0].id))
    db.add(GroupProfileAccess(group_id=g2.id, profile_id=profiles[1].id))
    db.add(GroupProfileAccess(group_id=g2.id, profile_id=profiles[2].id))
    db.add(OIDCGroupMapping(group_id=g1.id, oidc_group_name="team-a"))
    db.add(OIDCGroupMapping(group_id=g2.id, oidc_group_name="team-b"))

    user = User(username="multi", display_name="Multi", password_hash="!", role="user",
                oidc_provider="oidc", oidc_subject="multi-sub")
    db.add(user)
    db.commit()
    db.refresh(user)

    _sync_user_groups(db, user, {"sub": "multi-sub", "groups": ["team-a", "team-b"]})
    db.refresh(user)

    assert user.role == "user"
    access = db.query(UserProfileAccess).filter(UserProfileAccess.user_id == user.id).all()
    assert set(r.profile_id for r in access) == {profiles[0].id, profiles[1].id, profiles[2].id}


def test_oidc_group_sync_admin_wins(client: TestClient, db):
    """If any matched group has role admin, user becomes admin."""
    from app.models import Group, OIDCGroupMapping, User
    from app.routers.auth import _sync_user_groups

    _setup_and_login(client)

    g1 = Group(name="users-g", role="user")
    g2 = Group(name="admins-g", role="admin")
    db.add_all([g1, g2])
    db.flush()
    db.add(OIDCGroupMapping(group_id=g1.id, oidc_group_name="oidc-users"))
    db.add(OIDCGroupMapping(group_id=g2.id, oidc_group_name="oidc-admins"))

    user = User(username="mixed", display_name="Mixed", password_hash="!", role="user",
                oidc_provider="oidc", oidc_subject="mixed-sub")
    db.add(user)
    db.commit()
    db.refresh(user)

    _sync_user_groups(db, user, {"sub": "mixed-sub", "groups": ["oidc-users", "oidc-admins"]})
    db.refresh(user)

    assert user.role == "admin"


def test_oidc_group_sync_no_matching_groups_noop(client: TestClient, db):
    """If no OIDC groups match any mapping, sync is a no-op."""
    from app.models import User, UserProfileAccess
    from app.routers.auth import _sync_user_groups

    _setup_and_login(client)

    user = User(username="nomatch", display_name="No Match", password_hash="!", role="user",
                oidc_provider="oidc", oidc_subject="nomatch-sub")
    db.add(user)
    db.commit()
    db.refresh(user)

    _sync_user_groups(db, user, {"sub": "nomatch-sub", "groups": ["unknown-group"]})
    db.refresh(user)

    assert user.role == "user"
    access = db.query(UserProfileAccess).filter(UserProfileAccess.user_id == user.id).all()
    assert len(access) == 0


def test_oidc_group_sync_custom_claim_name(client: TestClient, db):
    """Groups sync respects the configurable groups_claim setting name."""
    from app.models import Group, GroupProfileAccess, OIDCGroupMapping, Setting, User, UserProfileAccess
    from app.routers.auth import _sync_user_groups

    _setup_and_login(client)
    _, profiles = _make_stream_and_profiles(db, count=1)

    # Set custom claim name
    db.add(Setting(key="oidc_groups_claim", value="roles"))

    g = Group(name="custom-claim-g", role="user")
    db.add(g)
    db.flush()
    db.add(GroupProfileAccess(group_id=g.id, profile_id=profiles[0].id))
    db.add(OIDCGroupMapping(group_id=g.id, oidc_group_name="viewer"))

    user = User(username="custom-claim", display_name="CC", password_hash="!", role="user",
                oidc_provider="oidc", oidc_subject="cc-sub")
    db.add(user)
    db.commit()
    db.refresh(user)

    # Default 'groups' key should NOT match
    _sync_user_groups(db, user, {"sub": "cc-sub", "groups": ["viewer"]})
    db.refresh(user)
    access = db.query(UserProfileAccess).filter(UserProfileAccess.user_id == user.id).all()
    assert len(access) == 0  # no match because claim is 'roles' not 'groups'

    # Using the correct 'roles' key should match
    _sync_user_groups(db, user, {"sub": "cc-sub", "roles": ["viewer"]})
    db.refresh(user)
    access = db.query(UserProfileAccess).filter(UserProfileAccess.user_id == user.id).all()
    assert len(access) == 1
    assert access[0].profile_id == profiles[0].id


def test_oidc_config_groups_claim_round_trip(client: TestClient, db):
    """Saving and reading groups_claim in OIDC config works."""
    from app.config import encrypt
    from app.models import Setting

    _setup_and_login(client)

    # GET before any config -> disabled
    resp = client.get("/api/auth/oidc/config")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False

    # PUT config with groups_claim
    resp = client.put("/api/auth/oidc/config", json={
        "issuer_url": "https://idp.example.com",
        "client_id": "cid",
        "client_secret": "csecret",
        "groups_claim": "realm_roles",
    })
    assert resp.status_code == 200

    # GET should return groups_claim
    resp = client.get("/api/auth/oidc/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["groups_claim"] == "realm_roles"
