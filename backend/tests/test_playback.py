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
        end_time=start_time + timedelta(seconds=duration) if duration else None,
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
    # Every segment gets a discontinuity marker because -reset_timestamps 1
    # resets PTS in each .ts file
    assert result.count("#EXT-X-DISCONTINUITY") == 2  # between segments 1-2 and 2-3


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


def test_playlist_endpoint(authed_client, db):
    profile = _create_profile(db)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 0), duration=300.0)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 5), duration=300.0)

    resp = authed_client.get(
        f"/api/playback/{profile.id}/playlist",
        params={"start": "2026-03-30T10:00:00", "end": "2026-03-30T11:00:00"},
    )

    assert resp.status_code == 200
    assert "application/vnd.apple.mpegurl" in resp.headers["content-type"]
    assert "#EXTM3U" in resp.text


def test_playlist_endpoint_no_data(authed_client, db):
    profile = _create_profile(db)

    resp = authed_client.get(
        f"/api/playback/{profile.id}/playlist",
        params={"start": "2026-03-30T10:00:00", "end": "2026-03-30T11:00:00"},
    )

    assert resp.status_code == 200
    assert "#EXTM3U" in resp.text
    assert "#EXT-X-ENDLIST" in resp.text


def test_segment_endpoint_file_missing(authed_client, db):
    profile = _create_profile(db)
    seg = _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 0))

    resp = authed_client.get(f"/api/playback/segment/{seg.id}")
    assert resp.status_code == 404
    assert "not found on disk" in resp.json()["detail"]


def test_segment_endpoint_file_exists(authed_client, db, tmp_path):
    profile = _create_profile(db)
    seg = _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 0), file_path="recordings/test.ts")

    fake_file = tmp_path / "recordings" / "test.ts"
    fake_file.parent.mkdir(parents=True, exist_ok=True)
    fake_file.write_bytes(b"\x00" * 188)

    with patch("app.routers.playback.settings") as mock_settings:
        mock_settings.DATA_DIR = str(tmp_path)
        resp = authed_client.get(f"/api/playback/segment/{seg.id}")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp2t"
    assert resp.headers["cache-control"] == "no-store"


def test_segment_range_request_no_cache(authed_client, db, tmp_path):
    """Byte-range segment responses must not be cached."""
    profile = _create_profile(db)
    seg = _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 0), file_path="recordings/test.ts")

    fake_file = tmp_path / "recordings" / "test.ts"
    fake_file.parent.mkdir(parents=True, exist_ok=True)
    fake_file.write_bytes(b"\x00" * 1024)

    with patch("app.routers.playback.settings") as mock_settings:
        mock_settings.DATA_DIR = str(tmp_path)
        resp = authed_client.get(f"/api/playback/segment/{seg.id}", headers={"Range": "bytes=0-187"})

    assert resp.status_code == 206
    assert resp.headers["cache-control"] == "no-store"


def test_segment_not_found(authed_client, db):
    resp = authed_client.get("/api/playback/segment/99999")
    assert resp.status_code == 404


def test_availability_basic(authed_client, db):
    profile = _create_profile(db)
    base = datetime(2026, 3, 30, 10, 0)
    _create_segment(db, profile.id, base, duration=300.0)
    _create_segment(db, profile.id, base + timedelta(seconds=300), duration=300.0)
    _create_segment(db, profile.id, base + timedelta(seconds=600), duration=300.0)

    resp = authed_client.get(
        f"/api/playback/{profile.id}/availability",
        params={"date": "2026-03-30"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


def test_availability_with_gaps(authed_client, db):
    profile = _create_profile(db)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 0), duration=300.0)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 14, 0), duration=300.0)

    resp = authed_client.get(
        f"/api/playback/{profile.id}/availability",
        params={"date": "2026-03-30"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_availability_merges_near_contiguous_segments(db):
    """Segments with sub-second gaps (typical FFmpeg behavior) merge into one range."""
    profile = _create_profile(db)
    # Simulate FFmpeg segments: 299.8s actual duration, 300s apart by filename
    _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 0), duration=299.8)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 5), duration=299.8)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 10), duration=299.8)

    ranges = get_availability_ranges(
        db, profile.id,
        datetime(2026, 3, 30, 0, 0),
        datetime(2026, 3, 31, 0, 0),
    )
    assert len(ranges) == 1  # Should merge, not be 3 separate bars


def test_availability_does_not_merge_real_gaps(db):
    """Segments separated by more than the tolerance stay separate."""
    profile = _create_profile(db)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 0), duration=300.0)
    # 10-second gap — beyond tolerance
    _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 5, 10), duration=300.0)

    ranges = get_availability_ranges(
        db, profile.id,
        datetime(2026, 3, 30, 0, 0),
        datetime(2026, 3, 31, 0, 0),
    )
    assert len(ranges) == 2


def test_playlist_discontinuity_on_every_segment(db):
    """Every segment gets a discontinuity marker due to -reset_timestamps 1."""
    profile = _create_profile(db)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 0), duration=299.8)
    _create_segment(db, profile.id, datetime(2026, 3, 30, 10, 5), duration=299.8)

    result = generate_playlist(db, profile.id, datetime(2026, 3, 30, 10, 0), datetime(2026, 3, 30, 11, 0))
    assert result.count("#EXT-X-DISCONTINUITY") == 1  # between the two segments
