"""Recording status and control endpoints."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import check_profile_access, get_accessible_profile_ids, get_current_user, require_admin
from app.models import RecordingSegment, User
from app.schemas import ProtectRequest, ProtectResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recording", tags=["recording"], dependencies=[Depends(get_current_user)])


@router.get("/status")
def get_recording_statuses(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return recording status for all active recording processes (filtered by access for non-admins)."""
    from app.services.recording import recording_manager

    all_statuses = recording_manager.get_all_statuses()

    accessible_ids = get_accessible_profile_ids(current_user, db)
    if accessible_ids is None:
        return all_statuses

    # all_statuses is a dict keyed by profile_id (int or str); filter to accessible
    if isinstance(all_statuses, dict):
        return {k: v for k, v in all_statuses.items() if int(k) in accessible_ids}
    # If it's a list, filter by profile_id field
    if isinstance(all_statuses, list):
        return [s for s in all_statuses if s.get("profile_id") in accessible_ids]
    return all_statuses


@router.get("/status/{profile_id}")
def get_recording_status(profile_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return recording status for a specific profile."""
    check_profile_access(current_user, profile_id, db)

    from app.services.recording import recording_manager

    return recording_manager.get_status(profile_id)


@router.post("/{profile_id}/protect", response_model=ProtectResponse)
def protect_segments(profile_id: int, body: ProtectRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mark all overlapping segments as protected."""
    check_profile_access(current_user, profile_id, db)

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
def unprotect_segments(profile_id: int, body: ProtectRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Clear protection on all overlapping segments."""
    check_profile_access(current_user, profile_id, db)

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
def get_segments_summary(profile_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return a summary of recording segments for a profile."""
    check_profile_access(current_user, profile_id, db)

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
async def verify_segments(profile_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Re-probe all segments and compare ffprobe duration vs DB duration.
    
    Returns a list of segments with their DB-stored duration and the
    freshly-probed duration, plus a mismatch flag.
    """
    check_profile_access(current_user, profile_id, db)

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


@router.delete("/all", status_code=200)
async def delete_all_recordings(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Delete ALL recording segments from database and disk. Destructive and irreversible.
    
    Admin-only. Stops all active recording processes, deletes all segment files,
    removes DB records, and restarts recording for enabled profiles.
    """
    import os
    import shutil
    from app.config import settings
    from app.services.recording import recording_manager

    # 1. Stop all active recordings
    await recording_manager.stop_all()

    # 2. Delete all segment records from DB
    count = db.query(RecordingSegment).delete()
    db.commit()

    # 3. Remove recordings directory from disk
    recordings_dir = os.path.join(settings.DATA_DIR, "recordings")
    removed_bytes = 0
    if os.path.isdir(recordings_dir):
        for root, dirs, files in os.walk(recordings_dir):
            for f in files:
                try:
                    fpath = os.path.join(root, f)
                    removed_bytes += os.path.getsize(fpath)
                except OSError:
                    pass
        shutil.rmtree(recordings_dir, ignore_errors=True)
        os.makedirs(recordings_dir, exist_ok=True)

    # 4. Restart recordings for enabled profiles
    await recording_manager.start_all()

    return {
        "status": "ok",
        "segments_deleted": count,
        "bytes_freed": removed_bytes,
    }
