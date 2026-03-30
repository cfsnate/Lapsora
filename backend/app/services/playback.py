"""Playback service: HLS playlist generation and availability queries."""

from datetime import datetime, timedelta

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import RecordingSegment


def generate_playlist(
    db: Session, profile_id: int, start_time: datetime, end_time: datetime
) -> str:
    segments = (
        db.query(RecordingSegment)
        .filter(
            and_(
                RecordingSegment.profile_id == profile_id,
                RecordingSegment.start_time >= start_time,
                RecordingSegment.start_time < end_time,
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
    segments = (
        db.query(
            RecordingSegment.start_time,
            RecordingSegment.duration_seconds,
        )
        .filter(
            and_(
                RecordingSegment.profile_id == profile_id,
                RecordingSegment.start_time >= day_start,
                RecordingSegment.start_time < day_end,
            )
        )
        .order_by(RecordingSegment.start_time.asc())
        .all()
    )

    ranges: list[dict] = []
    for start, duration in segments:
        end = start + timedelta(seconds=duration or 0)
        if ranges and start <= datetime.fromisoformat(ranges[-1]["end"]):
            if end.isoformat() > ranges[-1]["end"]:
                ranges[-1]["end"] = end.isoformat()
        else:
            ranges.append({"start": start.isoformat(), "end": end.isoformat()})

    return ranges
