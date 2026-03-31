"""Profile management endpoints."""

import logging
import os
import shutil

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import check_profile_access, check_profile_permission, get_accessible_profile_ids, get_current_user, require_admin
from app.models import Profile, Stream, User
from app.schemas import ProfileCreate, ProfileRead, ProfileUpdate
from app.services import scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["profiles"], dependencies=[Depends(get_current_user)])


@router.get("/streams/{stream_id}/profiles", response_model=list[ProfileRead])
def list_profiles(stream_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")
    q = db.query(Profile).filter(Profile.stream_id == stream_id)
    accessible_ids = get_accessible_profile_ids(current_user, db)
    if accessible_ids is not None:
        q = q.filter(Profile.id.in_(accessible_ids))
    return q.all()


@router.post("/streams/{stream_id}/profiles", response_model=ProfileRead, status_code=201)
def create_profile(stream_id: int, body: ProfileCreate, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    profile = Profile(stream_id=stream_id, **body.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)

    if profile.enabled:
        scheduler.add_capture_job(profile)

    return profile


@router.get("/profiles/{profile_id}", response_model=ProfileRead)
def get_profile(profile_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    check_profile_access(current_user, profile_id, db)
    return profile


@router.put("/profiles/{profile_id}", response_model=ProfileRead)
async def update_profile(profile_id: int, body: ProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    check_profile_permission(current_user, profile_id, "can_manage", db)

    update_data = body.model_dump(exclude_unset=True)
    needs_reschedule = any(
        k in update_data
        for k in ("interval_seconds", "enabled", "capture_mode", "active_start_time",
                   "active_end_time", "sun_events", "sun_offset_minutes",
                   "recording_enabled", "recording_mode", "recording_start_time",
                   "recording_end_time", "recording_sun_events", "recording_sun_offset_minutes",
                   "recording_days")
    )

    for key, value in update_data.items():
        setattr(profile, key, value)

    db.commit()
    db.refresh(profile)

    if needs_reschedule:
        if profile.enabled:
            scheduler.reschedule_capture_job(profile)
        else:
            scheduler.remove_capture_job(profile.id)

    recording_fields = (
        "recording_enabled", "recording_mode", "recording_start_time",
        "recording_end_time", "recording_sun_events",
        "recording_sun_offset_minutes", "recording_days",
        "segment_duration_seconds",
    )
    if any(k in update_data for k in recording_fields):
        from app.services.recording import recording_manager

        if profile.recording_enabled:
            await recording_manager.restart(profile.id)
        else:
            await recording_manager.stop(profile.id)

    return profile


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(profile_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    check_profile_permission(current_user, profile_id, "can_manage", db)

    scheduler.remove_capture_job(profile.id)

    from app.services.recording import recording_manager

    await recording_manager.stop(profile.id)

    # Remove capture files
    capture_dir = os.path.join(
        settings.DATA_DIR, "captures", str(profile.stream_id), str(profile.id)
    )
    if os.path.isdir(capture_dir):
        shutil.rmtree(capture_dir, ignore_errors=True)

    db.delete(profile)
    db.commit()


@router.post("/profiles/{profile_id}/enable", response_model=ProfileRead)
def enable_profile(profile_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    check_profile_permission(current_user, profile_id, "can_manage", db)

    profile.enabled = True
    db.commit()
    db.refresh(profile)

    scheduler.add_capture_job(profile)
    return profile


@router.post("/profiles/{profile_id}/disable", response_model=ProfileRead)
def disable_profile(profile_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    check_profile_permission(current_user, profile_id, "can_manage", db)

    profile.enabled = False
    db.commit()
    db.refresh(profile)

    scheduler.remove_capture_job(profile.id)
    return profile
