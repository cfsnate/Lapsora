"""Tests for clip export endpoints, quality presets, segment overlap, and queue independence."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.models import ClipExport, Profile, RecordingSegment, Stream


def _create_stream(db, stream_id=1, name="Test Stream"):
    existing = db.query(Stream).filter(Stream.id == stream_id).first()
    if existing:
        return existing
    s = Stream(id=stream_id, name=name, url="rtsp://test", source_type="rtsp")
    db.add(s)
    db.flush()
    return s


def _create_profile(db, stream_id=1, name="Test Profile"):
    _create_stream(db, stream_id)
    p = Profile(stream_id=stream_id, name=name)
    db.add(p)
    db.flush()
    return p


def _create_segment(db, profile_id, start_time, file_path, duration_seconds=10.0):
    seg = RecordingSegment(
        profile_id=profile_id,
        start_time=start_time,
        end_time=start_time + timedelta(seconds=duration_seconds),
        file_path=file_path,
        file_size=1000,
        duration_seconds=duration_seconds,
    )
    db.add(seg)
    db.flush()
    return seg


def _create_export(
    db, profile_id, start_time, end_time,
    status="pending", quality_preset="original", resolution="original",
):
    exp = ClipExport(
        profile_id=profile_id,
        start_time=start_time,
        end_time=end_time,
        status=status,
        quality_preset=quality_preset,
        resolution=resolution,
    )
    db.add(exp)
    db.flush()
    return exp


@patch("app.routers.exports.enqueue_export", new_callable=AsyncMock)
def test_create_export(mock_enqueue, client, db):
    profile = _create_profile(db)
    db.commit()
    mock_enqueue.return_value = {"clip_export_id": 1, "position": 1}

    resp = client.post("/api/exports/", json={
        "profile_id": profile.id,
        "start_time": "2026-01-01T10:00:00Z",
        "end_time": "2026-01-01T10:30:00Z",
    })
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert "id" in data

    export = db.query(ClipExport).get(data["id"])
    assert export is not None
    assert export.status == "pending"


@patch("app.routers.exports.enqueue_export", new_callable=AsyncMock)
def test_list_exports(mock_enqueue, client, db):
    profile = _create_profile(db)
    now = datetime.now(UTC)
    _create_export(db, profile.id, now - timedelta(hours=2), now - timedelta(hours=1), status="completed")
    _create_export(db, profile.id, now - timedelta(hours=1), now, status="pending")
    db.commit()

    resp = client.get("/api/exports/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["created_at"] >= data[1]["created_at"]


@patch("app.routers.exports.enqueue_export", new_callable=AsyncMock)
def test_list_exports_filter_status(mock_enqueue, client, db):
    profile = _create_profile(db)
    now = datetime.now(UTC)
    _create_export(db, profile.id, now - timedelta(hours=2), now - timedelta(hours=1), status="completed")
    _create_export(db, profile.id, now - timedelta(hours=1), now, status="pending")
    _create_export(db, profile.id, now, now + timedelta(hours=1), status="completed")
    db.commit()

    resp = client.get("/api/exports/?status=completed")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all(e["status"] == "completed" for e in data)


def test_quality_presets(db):
    profile = _create_profile(db)
    now = datetime.now(UTC)

    presets = ["original", "high", "medium", "low"]
    for preset in presets:
        _create_export(
            db, profile.id, now, now + timedelta(hours=1),
            quality_preset=preset,
        )
    db.commit()

    exports = db.query(ClipExport).filter(ClipExport.profile_id == profile.id).all()
    stored = [e.quality_preset for e in exports]
    for preset in presets:
        assert preset in stored


def test_resolution_conditional(db):
    profile = _create_profile(db)
    now = datetime.now(UTC)

    e1 = _create_export(
        db, profile.id, now, now + timedelta(hours=1),
        quality_preset="original", resolution="720p",
    )
    e2 = _create_export(
        db, profile.id, now, now + timedelta(hours=1),
        quality_preset="high", resolution="720p",
    )
    db.commit()

    db.refresh(e1)
    db.refresh(e2)
    assert e1.resolution == "720p"
    assert e2.resolution == "720p"
    assert e1.quality_preset == "original"
    assert e2.quality_preset == "high"


def test_segment_overlap_query(db):
    profile = _create_profile(db)
    base = datetime(2026, 1, 1, 10, 0)

    _create_segment(db, profile.id, base, "recordings/1/s1.ts", duration_seconds=600)
    _create_segment(db, profile.id, base + timedelta(minutes=10), "recordings/1/s2.ts", duration_seconds=600)
    _create_segment(db, profile.id, base + timedelta(minutes=20), "recordings/1/s3.ts", duration_seconds=600)
    _create_segment(db, profile.id, base + timedelta(minutes=30), "recordings/1/s4.ts", duration_seconds=600)
    _create_segment(db, profile.id, base + timedelta(minutes=40), "recordings/1/s5.ts", duration_seconds=600)
    db.commit()

    query_start = base + timedelta(minutes=15)
    query_end = base + timedelta(minutes=35)

    segments = (
        db.query(RecordingSegment)
        .filter(
            RecordingSegment.profile_id == profile.id,
            RecordingSegment.start_time < query_end,
        )
        .order_by(RecordingSegment.start_time.asc())
        .all()
    )
    segments = [
        s for s in segments
        if s.start_time + timedelta(seconds=s.duration_seconds or 0) > query_start
    ]

    assert len(segments) == 3
    assert segments[0].file_path == "recordings/1/s2.ts"
    assert segments[-1].file_path == "recordings/1/s4.ts"


@patch("app.routers.exports.enqueue_export", new_callable=AsyncMock)
def test_download_completed_export(mock_enqueue, client, db):
    profile = _create_profile(db)
    now = datetime.now(UTC)
    export = _create_export(
        db, profile.id, now, now + timedelta(hours=1), status="completed",
    )
    export.file_path = "exports/1/clip_1.mp4"
    db.commit()

    with patch("os.path.isfile", return_value=True), \
         patch("app.routers.exports.FileResponse", return_value=MagicMock(status_code=200)) as mock_fr:
        mock_fr.return_value.status_code = 200
        resp = client.get(f"/api/exports/{export.id}/download")

    assert resp.status_code == 200


@patch("app.routers.exports.enqueue_export", new_callable=AsyncMock)
def test_download_pending_export_404(mock_enqueue, client, db):
    profile = _create_profile(db)
    now = datetime.now(UTC)
    export = _create_export(db, profile.id, now, now + timedelta(hours=1), status="pending")
    db.commit()

    resp = client.get(f"/api/exports/{export.id}/download")
    assert resp.status_code == 404


@patch("app.routers.exports.enqueue_export", new_callable=AsyncMock)
def test_delete_export(mock_enqueue, client, db):
    profile = _create_profile(db)
    now = datetime.now(UTC)
    export = _create_export(
        db, profile.id, now, now + timedelta(hours=1), status="completed",
    )
    export.file_path = "exports/1/clip_1.mp4"
    db.commit()
    export_id = export.id

    with patch("os.path.isfile", return_value=True), \
         patch("os.unlink") as mock_unlink:
        resp = client.delete(f"/api/exports/{export_id}")

    assert resp.status_code == 204
    assert db.query(ClipExport).get(export_id) is None


def test_independent_queue(db):
    from app.services import generation_queue, export_queue

    assert generation_queue._queue is not export_queue._export_queue
