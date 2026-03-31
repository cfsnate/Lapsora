"""Recording status and control endpoints."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RecordingSegment
from app.schemas import ProtectRequest, ProtectResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recording", tags=["recording"])


@router.get("/status")
def get_recording_statuses():
    """Return recording status for all active recording processes."""
    from app.services.recording import recording_manager

    return recording_manager.get_all_statuses()


@router.get("/status/{profile_id}")
def get_recording_status(profile_id: int):
    """Return recording status for a specific profile."""
    from app.services.recording import recording_manager

    return recording_manager.get_status(profile_id)


@router.post("/{profile_id}/protect", response_model=ProtectResponse)
def protect_segments(profile_id: int, body: ProtectRequest, db: Session = Depends(get_db)):
    """Mark all overlapping segments as protected."""
    stmt = (
        update(RecordingSegment)
        .where(
            RecordingSegment.profile_id == profile_id,
            RecordingSegment.start_time < body.end_time,
            or_(
                RecordingSegment.end_time > body.start_time,
                RecordingSegment.end_time.is_(None),
            ),
        )
        .values(protected=True)
    )
    result = db.execute(stmt)
    db.commit()
    return ProtectResponse(affected_count=result.rowcount)


@router.post("/{profile_id}/unprotect", response_model=ProtectResponse)
def unprotect_segments(profile_id: int, body: ProtectRequest, db: Session = Depends(get_db)):
    """Clear protection on all overlapping segments."""
    stmt = (
        update(RecordingSegment)
        .where(
            RecordingSegment.profile_id == profile_id,
            RecordingSegment.start_time < body.end_time,
            or_(
                RecordingSegment.end_time > body.start_time,
                RecordingSegment.end_time.is_(None),
            ),
        )
        .values(protected=False)
    )
    result = db.execute(stmt)
    db.commit()
    return ProtectResponse(affected_count=result.rowcount)


@router.get("/{profile_id}/segments/summary")
def get_segments_summary(profile_id: int, db: Session = Depends(get_db)):
    """Return a summary of recording segments for a profile."""
    row = db.query(
        func.count(RecordingSegment.id).label("count"),
        func.coalesce(func.sum(RecordingSegment.file_size), 0).label("total_bytes"),
        func.coalesce(func.sum(RecordingSegment.duration_seconds), 0).label("total_duration"),
        func.min(RecordingSegment.start_time).label("earliest"),
        func.max(RecordingSegment.start_time).label("latest"),
    ).filter(
        RecordingSegment.profile_id == profile_id,
    ).one()

    return {
        "profile_id": profile_id,
        "segment_count": row.count,
        "total_bytes": row.total_bytes,
        "total_duration_seconds": float(row.total_duration) if row.total_duration else 0,
        "earliest": row.earliest.isoformat() + "Z" if row.earliest else None,
        "latest": row.latest.isoformat() + "Z" if row.latest else None,
    }


@router.get("/{profile_id}/segments/verify")
async def verify_segments(profile_id: int, db: Session = Depends(get_db)):
    """Re-probe all segments and compare ffprobe duration vs DB duration.
    
    Returns a list of segments with their DB-stored duration and the
    freshly-probed duration, plus a mismatch flag.
    """
    import os
    from app.config import settings
    from app.services.recording import _get_segment_duration

    segments = (
        db.query(RecordingSegment)
        .filter(RecordingSegment.profile_id == profile_id)
        .order_by(RecordingSegment.start_time.asc())
        .all()
    )

    results = []
    for seg in segments:
        abs_path = os.path.join(settings.DATA_DIR, seg.file_path)
        file_exists = os.path.isfile(abs_path)
        file_size = os.path.getsize(abs_path) if file_exists else 0
        probed_duration = None
        if file_exists:
            probed_duration = await _get_segment_duration(abs_path)

        db_dur = seg.duration_seconds
        mismatch = False
        if probed_duration is not None and db_dur is not None:
            mismatch = abs(probed_duration - db_dur) > 1.0

        results.append({
            "id": seg.id,
            "file_path": seg.file_path,
            "file_exists": file_exists,
            "file_size_bytes": file_size,
            "start_time": seg.start_time.isoformat() + "Z" if seg.start_time else None,
            "db_duration": db_dur,
            "probed_duration": round(probed_duration, 2) if probed_duration else None,
            "mismatch": mismatch,
        })

    mismatches = sum(1 for r in results if r["mismatch"])
    missing_duration = sum(1 for r in results if r["db_duration"] is None)
    missing_files = sum(1 for r in results if not r["file_exists"])

    return {
        "profile_id": profile_id,
        "total_segments": len(results),
        "mismatches": mismatches,
        "missing_duration": missing_duration,
        "missing_files": missing_files,
        "segments": results,
    }
