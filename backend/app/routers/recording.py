"""Recording status and control endpoints."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import or_, update
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
