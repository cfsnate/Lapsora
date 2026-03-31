"""Tests for per-profile permissions and group membership."""

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SETUP_URL = "/api/auth/setup"
LOGIN_URL = "/api/auth/login"
USERS_URL = "/api/auth/users"

ADMIN_PAYLOAD = {
    "username": "admin",
    "display_name": "Admin User",
    "password": "securepass123",
}
ADMIN_CREDS = {"username": "admin", "password": "securepass123"}

USER_PAYLOAD = {
    "username": "viewer",
    "display_name": "Viewer",
    "password": "viewerpass123",
    "role": "user",
}
USER_CREDS = {"username": "viewer", "password": "viewerpass123"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_admin(client: TestClient) -> TestClient:
    """Create admin via /setup and login."""
    client.post(SETUP_URL, json=ADMIN_PAYLOAD)
    resp = client.post(LOGIN_URL, json=ADMIN_CREDS)
    assert resp.status_code == 200
    return client


def _create_stream_and_profile(client: TestClient) -> tuple[int, int]:
    """Create a stream and a profile, return (stream_id, profile_id)."""
    resp = client.post("/api/streams/", json={"name": "Test Cam", "url": "rtsp://test"})
    assert resp.status_code == 201, f"Stream creation failed: {resp.json()}"
    stream_id = resp.json()["id"]
    with patch("app.routers.profiles.scheduler"):
        resp = client.post(f"/api/streams/{stream_id}/profiles", json={"name": "Main"})
    assert resp.status_code == 201, f"Profile creation failed: {resp.json()}"
    profile_id = resp.json()["id"]
    return stream_id, profile_id


def _create_user(client: TestClient) -> int:
    """Create a non-admin user, return user_id."""
    resp = client.post(USERS_URL, json=USER_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["id"]


def _login_as_user(client: TestClient) -> TestClient:
    """Login as the viewer user."""
    resp = client.post(LOGIN_URL, json=USER_CREDS)
    assert resp.status_code == 200
    return client


# ---------------------------------------------------------------------------
# Permission resolution via user profile access
# ---------------------------------------------------------------------------


def test_set_profile_permissions(client: TestClient):
    """Admin can set per-profile permission flags for a user."""
    _setup_admin(client)
    _, profile_id = _create_stream_and_profile(client)
    user_id = _create_user(client)

    perms = [{
        "profile_id": profile_id,
        "can_view": True,
        "can_export": True,
        "can_timelapse": False,
        "can_manage": False,
    }]
    resp = client.put(
        f"/api/auth/users/{user_id}/profiles",
        json={"profile_ids": [], "profile_permissions": perms},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["profile_permissions"]) == 1
    pp = data["profile_permissions"][0]
    assert pp["profile_id"] == profile_id
    assert pp["can_view"] is True
    assert pp["can_export"] is True
    assert pp["can_timelapse"] is False
    assert pp["can_manage"] is False


def test_get_profile_permissions(client: TestClient):
    """GET /users/{id}/profiles returns permission flags."""
    _setup_admin(client)
    _, profile_id = _create_stream_and_profile(client)
    user_id = _create_user(client)

    client.put(
        f"/api/auth/users/{user_id}/profiles",
        json={"profile_ids": [], "profile_permissions": [{
            "profile_id": profile_id,
            "can_view": True,
            "can_export": False,
            "can_timelapse": True,
            "can_manage": False,
        }]},
    )

    resp = client.get(f"/api/auth/users/{user_id}/profiles")
    assert resp.status_code == 200
    pp = resp.json()["profile_permissions"][0]
    assert pp["can_timelapse"] is True
    assert pp["can_export"] is False


# ---------------------------------------------------------------------------
# Group membership
# ---------------------------------------------------------------------------


def test_set_and_get_user_groups(client: TestClient):
    """Admin can assign a user to groups."""
    _setup_admin(client)
    user_id = _create_user(client)

    # Create a group
    resp = client.post("/api/auth/groups", json={"name": "Viewers", "role": "user"})
    assert resp.status_code == 201
    group_id = resp.json()["id"]

    # Assign user to group
    resp = client.put(f"/api/auth/users/{user_id}/groups", json={"group_ids": [group_id]})
    assert resp.status_code == 200
    assert resp.json()["group_ids"] == [group_id]

    # Read back
    resp = client.get(f"/api/auth/users/{user_id}/groups")
    assert resp.status_code == 200
    assert resp.json()["group_ids"] == [group_id]

    # Group read should show member
    resp = client.get("/api/auth/groups")
    assert resp.status_code == 200
    group_data = [g for g in resp.json() if g["id"] == group_id][0]
    assert user_id in group_data["member_user_ids"]


def test_user_admin_read_includes_group_ids(client: TestClient):
    """UserAdminRead now includes group_ids."""
    _setup_admin(client)
    user_id = _create_user(client)

    resp = client.post("/api/auth/groups", json={"name": "TestGroup"})
    group_id = resp.json()["id"]
    client.put(f"/api/auth/users/{user_id}/groups", json={"group_ids": [group_id]})

    resp = client.get(f"/api/auth/users/{user_id}")
    assert resp.status_code == 200
    assert group_id in resp.json()["group_ids"]


# ---------------------------------------------------------------------------
# Group-based profile access (merged permissions)
# ---------------------------------------------------------------------------


def test_group_profile_access_grants_view(client: TestClient):
    """User in a group with profile access can view that profile."""
    _setup_admin(client)
    _, profile_id = _create_stream_and_profile(client)
    user_id = _create_user(client)

    # Create group with profile access
    resp = client.post("/api/auth/groups", json={
        "name": "CamGroup",
        "profile_permissions": [{
            "profile_id": profile_id,
            "can_view": True,
            "can_export": False,
            "can_timelapse": False,
            "can_manage": False,
        }],
    })
    group_id = resp.json()["id"]

    # Assign user to group
    client.put(f"/api/auth/users/{user_id}/groups", json={"group_ids": [group_id]})

    # Login as user and try to view the profile
    _login_as_user(client)
    resp = client.get(f"/api/profiles/{profile_id}")
    assert resp.status_code == 200


def test_any_grant_wins_across_sources(client: TestClient):
    """If direct access has can_export=false but group has can_export=true, user can export."""
    _setup_admin(client)
    _, profile_id = _create_stream_and_profile(client)
    user_id = _create_user(client)

    # Direct access: view only
    client.put(f"/api/auth/users/{user_id}/profiles", json={
        "profile_ids": [],
        "profile_permissions": [{
            "profile_id": profile_id,
            "can_view": True,
            "can_export": False,
            "can_timelapse": False,
            "can_manage": False,
        }],
    })

    # Group access: can_export
    resp = client.post("/api/auth/groups", json={
        "name": "Exporters",
        "profile_permissions": [{
            "profile_id": profile_id,
            "can_view": True,
            "can_export": True,
            "can_timelapse": False,
            "can_manage": False,
        }],
    })
    group_id = resp.json()["id"]
    client.put(f"/api/auth/users/{user_id}/groups", json={"group_ids": [group_id]})

    # Verify merged permissions via the dependency directly
    from app.dependencies import get_profile_permissions
    from app.models import User

    # We need the db session from the fixture
    from app.database import get_db
    # Use the test client's overridden db
    db = next(client.app.dependency_overrides[get_db]())
    user = db.query(User).filter(User.id == user_id).first()
    perms = get_profile_permissions(user, profile_id, db)
    assert perms["can_view"] is True
    assert perms["can_export"] is True  # from group
    assert perms["can_timelapse"] is False
    assert perms["can_manage"] is False


# ---------------------------------------------------------------------------
# Endpoint enforcement
# ---------------------------------------------------------------------------


def test_export_denied_without_can_export(client: TestClient):
    """User with can_view but not can_export gets 403 on export creation."""
    _setup_admin(client)
    _, profile_id = _create_stream_and_profile(client)
    user_id = _create_user(client)

    # Grant view-only
    client.put(f"/api/auth/users/{user_id}/profiles", json={
        "profile_ids": [],
        "profile_permissions": [{
            "profile_id": profile_id,
            "can_view": True,
            "can_export": False,
            "can_timelapse": False,
            "can_manage": False,
        }],
    })

    _login_as_user(client)
    resp = client.post("/api/exports/", json={
        "profile_id": profile_id,
        "start_time": "2025-01-01T00:00:00Z",
        "end_time": "2025-01-01T01:00:00Z",
    })
    assert resp.status_code == 403


def test_profile_update_denied_without_can_manage(client: TestClient):
    """User with can_view but not can_manage gets 403 on profile update."""
    _setup_admin(client)
    _, profile_id = _create_stream_and_profile(client)
    user_id = _create_user(client)

    client.put(f"/api/auth/users/{user_id}/profiles", json={
        "profile_ids": [],
        "profile_permissions": [{
            "profile_id": profile_id,
            "can_view": True,
            "can_export": False,
            "can_timelapse": False,
            "can_manage": False,
        }],
    })

    _login_as_user(client)
    with patch("app.routers.profiles.scheduler"):
        resp = client.put(f"/api/profiles/{profile_id}", json={"name": "Hacked"})
    assert resp.status_code == 403


def test_profile_update_allowed_with_can_manage(client: TestClient):
    """User with can_manage can update a profile."""
    _setup_admin(client)
    _, profile_id = _create_stream_and_profile(client)
    user_id = _create_user(client)

    client.put(f"/api/auth/users/{user_id}/profiles", json={
        "profile_ids": [],
        "profile_permissions": [{
            "profile_id": profile_id,
            "can_view": True,
            "can_export": False,
            "can_timelapse": False,
            "can_manage": True,
        }],
    })

    _login_as_user(client)
    with patch("app.routers.profiles.scheduler"):
        resp = client.put(f"/api/profiles/{profile_id}", json={"name": "Renamed"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"


def test_no_access_returns_403(client: TestClient):
    """User with no access to a profile gets 403."""
    _setup_admin(client)
    _, profile_id = _create_stream_and_profile(client)
    _create_user(client)

    _login_as_user(client)
    resp = client.get(f"/api/profiles/{profile_id}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Group permission flags in CRUD
# ---------------------------------------------------------------------------


def test_group_profile_permissions_in_read(client: TestClient):
    """GroupRead includes profile_permissions with correct flags."""
    _setup_admin(client)
    _, profile_id = _create_stream_and_profile(client)

    resp = client.post("/api/auth/groups", json={
        "name": "WithPerms",
        "profile_permissions": [{
            "profile_id": profile_id,
            "can_view": True,
            "can_export": True,
            "can_timelapse": True,
            "can_manage": False,
        }],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["profile_permissions"]) == 1
    pp = data["profile_permissions"][0]
    assert pp["can_export"] is True
    assert pp["can_timelapse"] is True
    assert pp["can_manage"] is False


def test_legacy_profile_ids_still_work(client: TestClient):
    """Setting profile_ids without profile_permissions uses defaults."""
    _setup_admin(client)
    _, profile_id = _create_stream_and_profile(client)
    user_id = _create_user(client)

    resp = client.put(
        f"/api/auth/users/{user_id}/profiles",
        json={"profile_ids": [profile_id], "profile_permissions": []},
    )
    assert resp.status_code == 200
    pp = resp.json()["profile_permissions"][0]
    assert pp["can_view"] is True
    assert pp["can_export"] is False  # default
