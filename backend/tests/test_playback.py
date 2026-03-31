"""Tests for playback service and API endpoints."""

import os
from datetime import datetime, timedelta
from unittest.mock import patch

from app.models import Profile, RecordingSegment, Stream
from app.services.playback import generate_playlist, get_availability_ranges


def _create_profile(db, name="test-profile", recording_enabled=True):
    stream = Stream(name="test-stream", source_type="rtsp", url="rtsp://test", enabled=True)
    db.add(stream)
    db.flush()
    profile = Profile(
        stream_id=stream.id,
        name=name,
        recording_enabled=recording_enabled,
        interval_seconds=60,
        quality=85,
    )
    db.add(profile)
    db.flush()
    return profile


def _create_segment(db, profile_id, start_time, duration=300.0, file_path=None):
    if file_path is None:
        file_path = f"recordings/{profile_id}/{start_time.strftime('%Y%m%d_%H%M%S')}.ts"
    seg = RecordingSegment(
        profile_id=profile_id,
        start_time=start_time,
        duration_seconds=duration,
        file_path=file_path,
        file_size=1024000,
    )
    db.add(seg)
    db.flush()
    return seg


def test_generate_playlist_basic(db):
    profile = _create_profile(db)
    base = datetime(2026, 3, 30, 10, 0)
    _create_segment(db, profile.id, base, duration=300.0)
    _create_segment(db, profile.id, base + timedelta(seconds=300), duration=300.0)
    _create_segment(db, profile.id, base + timedelta(seconds=600), duration=300.0)

    result = generate_playlist(db, profile.id, datetime(2026, 3, 30, 10, 0), datetime(2026, 3, 30, 11, 0))

    assert "#EXTM3U" in result
    assert "#EXT-X-PLAYLIST-TYPE:VOD" in result
    assert "#EXT-X-ENDLIST" in result
    assert "#EXTINF:300.0," in result
    assert "/api/playback/segment/" in result
    assert "#EXT-X-DISCONTINUITY" not in result


def test_generate_playlist_with_gap(db):
    profile = _create_profile(db)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 0), duration=300.0)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 11, 5), duration=300.0)

    result = generate_playlist(db, profile.id, datetime(2026, 3, 30, 10, 0), datetime(2026, 3, 30, 12, 0))

    assert "#EXT-X-DISCONTINUITY" in result
    assert result.count("#EXT-X-PROGRAM-DATE-TIME") == 2


def test_generate_playlist_empty(db):
    profile = _create_profile(db)
    result = generate_playlist(db, profile.id, datetime(2026, 3, 30, 10, 0), datetime(2026, 3, 30, 11, 0))
    assert result == ""


def test_playlist_endpoint(client, db):
    profile = _create_profile(db)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 0), duration=300.0)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 5), duration=300.0)

    resp = client.get(
        f"/api/playback/{profile.id}/playlist",
        params={"start": "2026-03-30T10:00:00", "end": "2026-03-30T11:00:00"},
    )

    assert resp.status_code == 200
    assert "application/vnd.apple.mpegurl" in resp.headers["content-type"]
    assert "#EXTM3U" in resp.text


def test_playlist_endpoint_no_data(client, db):
    profile = _create_profile(db)

    resp = client.get(
        f"/api/playback/{profile.id}/playlist",
        params={"start": "2026-03-30T10:00:00", "end": "2026-03-30T11:00:00"},
    )

    # Empty range returns a valid empty VOD playlist (200) rather than 404,
    # so HLS.js doesn't fatal on the response.
    assert resp.status_code == 200
    assert "#EXTM3U" in resp.text
    assert "#EXT-X-ENDLIST" in resp.text


def test_segment_endpoint_file_missing(client, db):
    profile = _create_profile(db)
    seg = _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 0))

    resp = client.get(f"/api/playback/segment/{seg.id}")
    assert resp.status_code == 404
    assert "not found on disk" in resp.json()["detail"]


def test_segment_endpoint_file_exists(client, db, tmp_path):
    profile = _create_profile(db)
    seg = _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 0), file_path="recordings/test.ts")

    fake_file = tmp_path / "recordings" / "test.ts"
    fake_file.parent.mkdir(parents=True, exist_ok=True)
    fake_file.write_bytes(b"\x00" * 188)

    with patch("app.routers.playback.settings") as mock_settings:
        mock_settings.DATA_DIR = str(tmp_path)
        resp = client.get(f"/api/playback/segment/{seg.id}")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp2t"


def test_segment_not_found(client, db):
    resp = client.get("/api/playback/segment/99999")
    assert resp.status_code == 404


def test_availability_basic(client, db):
    profile = _create_profile(db)
    base = datetime(2026, 3, 30, 10, 0)
    _create_segment(db, profile.id, base, duration=300.0)
    _create_segment(db, profile.id, base + timedelta(seconds=300), duration=300.0)
    _create_segment(db, profile.id, base + timedelta(seconds=600), duration=300.0)

    resp = client.get(
        f"/api/playback/{profile.id}/availability",
        params={"date": "2026-03-30"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1  # contiguous segments merge into one range


def test_availability_with_gaps(client, db):
    profile = _create_profile(db)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 0), duration=300.0)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 14, 0), duration=300.0)

    resp = client.get(
        f"/api/playback/{profile.id}/availability",
        params={"date": "2026-03-30"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2  # gap separates into two ranges
