"""Recording status and control endpoints."""

import logging

from fastapi import APIRouter

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
