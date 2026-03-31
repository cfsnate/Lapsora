"""Playback service: HLS playlist generation and availability queries."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import RecordingSegment


def _strip_tz(dt: datetime) -> datetime:
    """Strip timezone info for SQLite string comparison compatibility."""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


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

        if prev_end is not None and seg.start_time > prev_end + timedelta(seconds=1):
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

    ranges: list[dict] = []
    for start, duration in segments:
        if duration is not None:
            end = start + timedelta(seconds=duration)
        else:
            # In-progress segment: extend to now
            end = now

        start_str = start.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        end_str = end.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        if ranges and start <= datetime.fromisoformat(ranges[-1]["end"].rstrip("Z")):
            if end_str > ranges[-1]["end"]:
                ranges[-1]["end"] = end_str
        else:
            ranges.append({"start": start_str, "end": end_str})

    return ranges
