"""Playback API: HLS playlists, segment serving, and availability queries."""

import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import RecordingSegment
from app.services.playback import generate_playlist, get_availability_ranges

router = APIRouter(prefix="/api/playback", tags=["playback"])


@router.get("/{profile_id}/playlist")
def get_playlist(
    profile_id: int,
    start: datetime = Query(...),
    end: datetime = Query(...),
    db: Session = Depends(get_db),
):
    playlist = generate_playlist(db, profile_id, start, end)
    if not playlist:
        raise HTTPException(status_code=404, detail="No recordings found in range")
    return Response(content=playlist, media_type="application/vnd.apple.mpegurl")


@router.get("/segment/{segment_id}")
def get_segment(segment_id: int, db: Session = Depends(get_db)):
    segment = db.get(RecordingSegment, segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    abs_path = os.path.join(settings.DATA_DIR, segment.file_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Segment file not found on disk")

    return FileResponse(abs_path, media_type="video/mp2t")


@router.get("/{profile_id}/availability")
def get_availability(
    profile_id: int,
    date: str = Query(...),
    days: int = Query(default=1),
    db: Session = Depends(get_db),
):
    day_start = datetime.strptime(date, "%Y-%m-%d")
    day_end = day_start + timedelta(days=days)
    return get_availability_ranges(db, profile_id, day_start, day_end)
