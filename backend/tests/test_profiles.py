from unittest.mock import patch


def _create_stream(client):
    resp = client.post("/api/streams/", json={"name": "S", "url": "rtsp://x"})
    return resp.json()["id"]


def _create_profile(client, stream_id, name="Profile 1"):
    with patch("app.routers.profiles.scheduler"):
        return client.post(
            f"/api/streams/{stream_id}/profiles",
            json={"name": name, "interval_seconds": 30},
        )


def test_create_profile(authed_client):
    sid = _create_stream(authed_client)
    resp = _create_profile(authed_client, sid)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Profile 1"
    assert data["stream_id"] == sid
    assert data["interval_seconds"] == 30


def test_list_profiles(authed_client):
    sid = _create_stream(authed_client)
    _create_profile(authed_client, sid, "P1")
    _create_profile(authed_client, sid, "P2")
    resp = authed_client.get(f"/api/streams/{sid}/profiles")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_profile(authed_client):
    sid = _create_stream(authed_client)
    create_resp = _create_profile(authed_client, sid)
    pid = create_resp.json()["id"]
    resp = authed_client.get(f"/api/profiles/{pid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == pid


def test_update_profile(authed_client):
    sid = _create_stream(authed_client)
    create_resp = _create_profile(authed_client, sid)
    pid = create_resp.json()["id"]
    with patch("app.routers.profiles.scheduler"):
        resp = authed_client.put(
            f"/api/profiles/{pid}", json={"interval_seconds": 120}
        )
    assert resp.status_code == 200
    assert resp.json()["interval_seconds"] == 120


def test_delete_profile(authed_client):
    sid = _create_stream(authed_client)
    create_resp = _create_profile(authed_client, sid)
    pid = create_resp.json()["id"]
    with patch("app.routers.profiles.scheduler"):
        resp = authed_client.delete(f"/api/profiles/{pid}")
    assert resp.status_code == 204
    resp = authed_client.get(f"/api/profiles/{pid}")
    assert resp.status_code == 404


def test_create_profile_nonexistent_stream(authed_client):
    with patch("app.routers.profiles.scheduler"):
        resp = authed_client.post(
            "/api/streams/9999/profiles",
            json={"name": "X", "interval_seconds": 60},
        )
    assert resp.status_code == 404


def test_create_profile_with_recording(authed_client):
    sid = _create_stream(authed_client)
    with patch("app.routers.profiles.scheduler"):
        resp = authed_client.post(
            f"/api/streams/{sid}/profiles",
            json={
                "name": "Rec Profile",
                "interval_seconds": 60,
                "recording_enabled": True,
                "recording_mode": "scheduled",
                "recording_start_time": "08:00",
                "recording_end_time": "20:00",
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["recording_enabled"] is True
    assert data["recording_mode"] == "scheduled"
    assert data["recording_start_time"] == "08:00"
    assert data["recording_end_time"] == "20:00"


def test_update_profile_recording_settings(authed_client):
    sid = _create_stream(authed_client)
    create_resp = _create_profile(authed_client, sid)
    pid = create_resp.json()["id"]
    with patch("app.routers.profiles.scheduler"):
        resp = authed_client.put(
            f"/api/profiles/{pid}",
            json={"recording_enabled": True, "segment_duration_seconds": 300},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["recording_enabled"] is True
    assert data["segment_duration_seconds"] == 300


def test_recording_disabled_by_default(authed_client):
    sid = _create_stream(authed_client)
    resp = _create_profile(authed_client, sid)
    data = resp.json()
    assert data["recording_enabled"] is False
    assert data["recording_mode"] == "always"
    assert data["segment_duration_seconds"] == 300
    assert data["recording_days"] == ""


def test_create_profile_scheduled_recording(authed_client):
    sid = _create_stream(authed_client)
    with patch("app.routers.profiles.scheduler"):
        resp = authed_client.post(
            f"/api/streams/{sid}/profiles",
            json={
                "name": "Sched Rec",
                "interval_seconds": 60,
                "recording_mode": "scheduled",
                "recording_start_time": "22:00",
                "recording_end_time": "06:00",
                "recording_days": "mon,wed,fri",
            },
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["recording_mode"] == "scheduled"
    assert data["recording_start_time"] == "22:00"
    assert data["recording_end_time"] == "06:00"
    assert data["recording_days"] == "mon,wed,fri"


def test_update_profile_sun_recording(authed_client):
    sid = _create_stream(authed_client)
    create_resp = _create_profile(authed_client, sid)
    pid = create_resp.json()["id"]
    with patch("app.routers.profiles.scheduler"):
        resp = authed_client.put(
            f"/api/profiles/{pid}",
            json={
                "recording_mode": "sun",
                "recording_sun_offset_minutes": 30,
                "recording_sun_events": "daylight,golden_hour",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["recording_mode"] == "sun"
    assert data["recording_sun_offset_minutes"] == 30
    assert data["recording_sun_events"] == "daylight,golden_hour"


def test_segment_duration_validation(authed_client):
    sid = _create_stream(authed_client)
    with patch("app.routers.profiles.scheduler"):
        resp = authed_client.post(
            f"/api/streams/{sid}/profiles",
            json={"name": "Bad", "interval_seconds": 60, "segment_duration_seconds": 10},
        )
    assert resp.status_code == 422

    with patch("app.routers.profiles.scheduler"):
        resp = authed_client.post(
            f"/api/streams/{sid}/profiles",
            json={"name": "Bad", "interval_seconds": 60, "segment_duration_seconds": 5000},
        )
    assert resp.status_code == 422

    with patch("app.routers.profiles.scheduler"):
        resp = authed_client.post(
            f"/api/streams/{sid}/profiles",
            json={"name": "Good", "interval_seconds": 60, "segment_duration_seconds": 600},
        )
    assert resp.status_code == 201
