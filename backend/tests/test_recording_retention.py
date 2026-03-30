"""Tests for recording retention, cleanup, protection, and storage stats."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models import Profile, RecordingSegment, Setting, Stream


def _create_stream(db, stream_id=1, name="Test Stream"):
    existing = db.query(Stream).filter(Stream.id == stream_id).first()
    if existing:
        return existing
    s = Stream(id=stream_id, name=name, url="rtsp://test", source_type="rtsp")
    db.add(s)
    db.flush()
    return s


def _create_profile(db, stream_id=1, name="Test Profile", recording_retention_days=None, recording_enabled=True):
    _create_stream(db, stream_id)
    p = Profile(
        stream_id=stream_id,
        name=name,
        recording_enabled=recording_enabled,
        recording_retention_days=recording_retention_days,
    )
    db.add(p)
    db.flush()
    return p


def _create_segment(db, profile_id, start_time, file_path, file_size=1000, protected=False, end_time=None):
    seg = RecordingSegment(
        profile_id=profile_id,
        start_time=start_time,
        end_time=end_time,
        file_path=file_path,
        file_size=file_size,
        protected=protected,
    )
    db.add(seg)
    db.flush()
    return seg


def test_cleanup_deletes_expired_segments(db):
    profile = _create_profile(db, recording_retention_days=7)
    now = datetime.now(UTC)

    _create_segment(db, profile.id, now - timedelta(days=10), "recordings/1/old.ts")
    _create_segment(db, profile.id, now - timedelta(days=5), "recordings/1/mid.ts")
    _create_segment(db, profile.id, now - timedelta(days=1), "recordings/1/new.ts")
    db.commit()

    from app.services.retention import run_recording_cleanup

    with patch("app.services.retention.SessionLocal", return_value=db), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink") as mock_unlink, \
         patch("os.path.isdir", return_value=False), \
         patch("app.services.retention.settings") as mock_settings:
        mock_settings.DATA_DIR = "/data"
        result = asyncio.run(run_recording_cleanup(profile.id, 7))

    assert result["segments_deleted"] == 1
    assert mock_unlink.call_count == 1
    remaining = db.query(RecordingSegment).filter(RecordingSegment.profile_id == profile.id).count()
    assert remaining == 2


def test_effective_retention_override(db):
    profile = _create_profile(db, recording_retention_days=30)
    db.add(Setting(key="default_recording_retention_days", value="7"))
    db.flush()

    from app.services.retention import _get_effective_retention

    assert _get_effective_retention(profile, db) == 30

    profile.recording_retention_days = None
    db.flush()
    assert _get_effective_retention(profile, db) == 7

    db.query(Setting).filter(Setting.key == "default_recording_retention_days").delete()
    db.flush()
    assert _get_effective_retention(profile, db) == 14


def test_batch_deletion(db):
    profile = _create_profile(db)
    now = datetime.now(UTC)

    for i in range(600):
        _create_segment(db, profile.id, now - timedelta(days=30, hours=i), f"recordings/1/seg_{i}.ts")
    db.commit()

    from app.services.retention import run_recording_cleanup

    commit_calls = []
    original_commit = db.commit

    def tracking_commit():
        commit_calls.append(1)
        original_commit()

    with patch("app.services.retention.SessionLocal", return_value=db), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"), \
         patch("os.path.isdir", return_value=False), \
         patch("app.services.retention.settings") as mock_settings, \
         patch.object(db, "commit", side_effect=tracking_commit):
        mock_settings.DATA_DIR = "/data"
        result = asyncio.run(run_recording_cleanup(profile.id, 1))

    assert result["segments_deleted"] == 600
    assert len(commit_calls) >= 2


def test_emergency_cleanup_oldest_first(db):
    profile = _create_profile(db)
    now = datetime.now(UTC)

    seg_old = _create_segment(db, profile.id, now - timedelta(days=10), "recordings/1/old.ts", file_size=5000)
    seg_mid = _create_segment(db, profile.id, now - timedelta(days=5), "recordings/1/mid.ts", file_size=5000)
    seg_new = _create_segment(db, profile.id, now - timedelta(days=1), "recordings/1/new.ts", file_size=5000)
    db.commit()

    call_count = [0]
    def mock_disk_usage(path):
        call_count[0] += 1
        if call_count[0] <= 1:
            return MagicMock(total=100_000, used=95_000, free=5_000)
        return MagicMock(total=100_000, used=75_000, free=25_000)

    from app.services.retention import run_emergency_recording_cleanup

    with patch("app.services.retention.SessionLocal", return_value=db), \
         patch("shutil.disk_usage", side_effect=mock_disk_usage), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"), \
         patch("app.services.retention.settings") as mock_settings:
        mock_settings.DATA_DIR = "/data"
        result = asyncio.run(run_emergency_recording_cleanup(target_pct=80))

    assert result["segments_deleted"] > 0
    remaining_ids = [s.id for s in db.query(RecordingSegment).all()]
    assert seg_new.id in remaining_ids


def test_orphan_cleanup(db):
    profile = _create_profile(db)
    now = datetime.now(UTC)

    _create_segment(db, profile.id, now - timedelta(days=5), "recordings/1/exists.ts")
    _create_segment(db, profile.id, now - timedelta(days=5), "recordings/1/missing.ts")
    db.commit()

    def selective_exists(path):
        return "exists.ts" in path

    from app.services.retention import run_recording_cleanup

    with patch("app.services.retention.SessionLocal", return_value=db), \
         patch("os.path.exists", side_effect=selective_exists), \
         patch("os.unlink"), \
         patch("os.path.isdir", return_value=False), \
         patch("app.services.retention.settings") as mock_settings:
        mock_settings.DATA_DIR = "/data"
        result = asyncio.run(run_recording_cleanup(profile.id, 0))

    assert result["orphan_records_cleaned"] >= 1


def test_protected_segments_exempt(db):
    profile = _create_profile(db, recording_retention_days=1)
    now = datetime.now(UTC)

    _create_segment(db, profile.id, now - timedelta(days=5), "recordings/1/protected.ts", protected=True)
    _create_segment(db, profile.id, now - timedelta(days=5), "recordings/1/unprotected.ts", protected=False)
    db.commit()

    from app.services.retention import run_recording_cleanup

    with patch("app.services.retention.SessionLocal", return_value=db), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"), \
         patch("os.path.isdir", return_value=False), \
         patch("app.services.retention.settings") as mock_settings:
        mock_settings.DATA_DIR = "/data"
        result = asyncio.run(run_recording_cleanup(profile.id, 1))

    assert result["segments_deleted"] == 1
    remaining = db.query(RecordingSegment).filter(RecordingSegment.profile_id == profile.id).all()
    assert len(remaining) == 1
    assert remaining[0].protected is True


def test_protect_time_range(client, db):
    profile = _create_profile(db)

    seg_a = _create_segment(
        db, profile.id,
        datetime(2026, 1, 1, 10, 0, tzinfo=UTC), "recordings/1/a.ts",
        end_time=datetime(2026, 1, 1, 10, 30, tzinfo=UTC),
    )
    seg_b = _create_segment(
        db, profile.id,
        datetime(2026, 1, 1, 11, 0, tzinfo=UTC), "recordings/1/b.ts",
        end_time=datetime(2026, 1, 1, 11, 30, tzinfo=UTC),
    )
    seg_c = _create_segment(
        db, profile.id,
        datetime(2026, 1, 1, 12, 0, tzinfo=UTC), "recordings/1/c.ts",
        end_time=datetime(2026, 1, 1, 12, 30, tzinfo=UTC),
    )
    db.commit()

    resp = client.post(
        f"/api/recording/{profile.id}/protect",
        json={"start_time": "2026-01-01T10:45:00Z", "end_time": "2026-01-01T12:15:00Z"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["affected_count"] == 2

    db.refresh(seg_a)
    db.refresh(seg_b)
    db.refresh(seg_c)
    assert seg_a.protected is False
    assert seg_b.protected is True
    assert seg_c.protected is True


def test_unprotect_time_range(client, db):
    profile = _create_profile(db)

    seg1 = _create_segment(
        db, profile.id,
        datetime(2026, 1, 1, 10, 0, tzinfo=UTC), "recordings/1/s1.ts",
        end_time=datetime(2026, 1, 1, 10, 30, tzinfo=UTC),
        protected=True,
    )
    seg2 = _create_segment(
        db, profile.id,
        datetime(2026, 1, 1, 11, 0, tzinfo=UTC), "recordings/1/s2.ts",
        end_time=datetime(2026, 1, 1, 11, 30, tzinfo=UTC),
        protected=True,
    )
    db.commit()

    resp = client.post(
        f"/api/recording/{profile.id}/unprotect",
        json={"start_time": "2026-01-01T09:00:00Z", "end_time": "2026-01-01T12:00:00Z"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["affected_count"] == 2

    db.refresh(seg1)
    db.refresh(seg2)
    assert seg1.protected is False
    assert seg2.protected is False


def test_recording_storage_stats(db):
    p1 = _create_profile(db, name="Profile A")
    p2 = _create_profile(db, name="Profile B")
    now = datetime.now(UTC)

    _create_segment(db, p1.id, now - timedelta(days=5), "recordings/1/a.ts", file_size=2000)
    _create_segment(db, p1.id, now - timedelta(days=1), "recordings/1/b.ts", file_size=3000, protected=True)
    _create_segment(db, p2.id, now - timedelta(days=3), "recordings/2/c.ts", file_size=4000)
    db.commit()

    from app.services.retention import get_recording_storage_stats

    with patch("app.services.retention.SessionLocal", return_value=db):
        stats = get_recording_storage_stats()

    assert stats["total_segments"] == 3
    assert stats["total_bytes"] == 9000
    assert len(stats["profiles"]) == 2

    p1_stats = next(p for p in stats["profiles"] if p["profile_id"] == p1.id)
    assert p1_stats["segment_count"] == 2
    assert p1_stats["total_bytes"] == 5000
    assert p1_stats["protected_count"] == 1
    assert p1_stats["oldest_recording"] is not None
    assert p1_stats["newest_recording"] is not None

    p2_stats = next(p for p in stats["profiles"] if p["profile_id"] == p2.id)
    assert p2_stats["segment_count"] == 1
    assert p2_stats["total_bytes"] == 4000
    assert p2_stats["protected_count"] == 0
