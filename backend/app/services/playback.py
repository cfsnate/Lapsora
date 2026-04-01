"""Playback service: HLS playlist generation and availability queries."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import RecordingSegment

# Maximum gap (seconds) between two segments that are still considered
# contiguous.  Covers sub-second FFmpeg duration imprecision and minor
# scheduling jitter without papering over real recording outages.
CONTINUITY_GAP_TOLERANCE = 5


def _strip_tz(dt: datetime) -> datetime:
    """Strip timezone info for SQLite string comparison compatibility."""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _seg_end(seg, now: datetime) -> datetime:
    """Return end_time for a segment, falling back to start + duration or now."""
    if seg.end_time is not None:
        return seg.end_time
    if seg.duration_seconds is not None:
        return seg.start_time + timedelta(seconds=seg.duration_seconds)
    return now


def generate_playlist(
    db: Session, profile_id: int, start_time: datetime, end_time: datetime
) -> str:
    segments = (
        db.query(RecordingSegment)
        .filter(
            and_(
                RecordingSegment.profile_id == profile_id,
                RecordingSegment.start_time >= _strip_tz(start_time),
                RecordingSegment.start_time < _strip_tz(end_time),
            )
        )
        .order_by(RecordingSegment.start_time.asc())
        .all()
    )

    if not segments:
        return ""

    now = datetime.now(UTC).replace(tzinfo=None)

    # For in-progress segments (duration=NULL), estimate duration from
    # elapsed time since start.
    durations = []
    for s in segments:
        if s.duration_seconds is not None:
            durations.append(s.duration_seconds)
        else:
            durations.append((now - s.start_time).total_seconds())

    max_duration = max(durations) if durations else 10

    lines: list[str] = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{int(max_duration) + 1}",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]

    prev_end: datetime | None = None
    for seg in segments:
        if seg.duration_seconds is not None:
            dur = seg.duration_seconds
        else:
            # In-progress segment: use elapsed time as provisional duration
            dur = max(1.0, (now - seg.start_time).total_seconds())

        # Every segment needs a discontinuity marker because FFmpeg records
        # with -reset_timestamps 1, resetting each .ts file's PTS to 0.
        # Without this, HLS.js builds a cumulative media timeline that
        # doesn't match the actual PTS, causing seeks to land wrong.
        if prev_end is not None:
            lines.append("#EXT-X-DISCONTINUITY")

        lines.append(
            f"#EXT-X-PROGRAM-DATE-TIME:{seg.start_time.strftime('%Y-%m-%dT%H:%M:%S')}.000Z"
        )
        lines.append(f"#EXTINF:{dur:.1f},")
        lines.append(f"/api/playback/segment/{seg.id}")

        prev_end = seg.start_time + timedelta(seconds=dur)

    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines)


def get_availability_ranges(
    db: Session, profile_id: int, day_start: datetime, day_end: datetime
) -> list[dict]:
    segments = (
        db.query(
            RecordingSegment.start_time,
            RecordingSegment.end_time,
            RecordingSegment.duration_seconds,
        )
        .filter(
            and_(
                RecordingSegment.profile_id == profile_id,
                RecordingSegment.start_time >= _strip_tz(day_start),
                RecordingSegment.start_time < _strip_tz(day_end),
            )
        )
        .order_by(RecordingSegment.start_time.asc())
        .all()
    )

    now = datetime.now(UTC).replace(tzinfo=None)
    tolerance = timedelta(seconds=CONTINUITY_GAP_TOLERANCE)

    # Build ranges using datetime objects, serialize at the end
    merged: list[tuple[datetime, datetime]] = []
    for start, end_time, duration in segments:
        if end_time is not None:
            end = end_time
        elif duration is not None:
            end = start + timedelta(seconds=duration)
        else:
            end = now

        if merged and start <= merged[-1][1] + tolerance:
            # Extend existing range if this segment's end is later
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))

    return [
        {
            "start": s.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            "end": e.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
        }
        for s, e in merged
    ]
