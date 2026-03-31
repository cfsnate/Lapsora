"""Playback service: HLS playlist generation and availability queries."""

from datetime import datetime, timedelta

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import RecordingSegment


def generate_playlist(
    db: Session, profile_id: int, start_time: datetime, end_time: datetime
) -> str:
    # Strip timezone info before querying SQLite — SQLAlchemy renders aware
    # datetimes as 'YYYY-MM-DDTHH:MM:SS+00:00' which compares incorrectly
    # against SQLite's naive 'YYYY-MM-DD HH:MM:SS' strings (T > space).
    start_naive = start_time.replace(tzinfo=None) if start_time.tzinfo else start_time
    end_naive = end_time.replace(tzinfo=None) if end_time.tzinfo else end_time

    segments = (
        db.query(RecordingSegment)
        .filter(
            and_(
                RecordingSegment.profile_id == profile_id,
                RecordingSegment.start_time >= start_naive,
                RecordingSegment.start_time < end_naive,
            )
        )
        .order_by(RecordingSegment.start_time.asc())
        .all()
    )

    if not segments:
        return ""

    durations = [s.duration_seconds for s in segments if s.duration_seconds is not None]
    max_duration = max(durations) if durations else 10

    lines: list[str] = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{int(max_duration) + 1}",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]

    prev_end: datetime | None = None
    for seg in segments:
        dur = seg.duration_seconds if seg.duration_seconds is not None else 10.0

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
    # Strip timezone before SQLite query — same naive/aware mismatch as generate_playlist
    start_naive = day_start.replace(tzinfo=None) if day_start.tzinfo else day_start
    end_naive = day_end.replace(tzinfo=None) if day_end.tzinfo else day_end

    segments = (
        db.query(
            RecordingSegment.start_time,
            RecordingSegment.duration_seconds,
        )
        .filter(
            and_(
                RecordingSegment.profile_id == profile_id,
                RecordingSegment.start_time >= start_naive,
                RecordingSegment.start_time < end_naive,
            )
        )
        .order_by(RecordingSegment.start_time.asc())
        .all()
    )

    ranges: list[dict] = []
    for start, duration in segments:
        end = start + timedelta(seconds=duration or 0)
        # Append Z so the browser parses these as UTC, not local time
        start_str = start.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        end_str = end.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        if ranges and start <= datetime.fromisoformat(ranges[-1]["end"].rstrip("Z")):
            if end_str > ranges[-1]["end"]:
                ranges[-1]["end"] = end_str
        else:
            ranges.append({"start": start_str, "end": end_str})

    return ranges
