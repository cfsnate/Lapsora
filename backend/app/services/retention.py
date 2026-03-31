"""Data retention and storage cleanup service."""

import logging
import os
import shutil
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Capture, Profile, RecordingSegment, Setting, Timelapse
from app.services.recording import recording_dir

logger = logging.getLogger(__name__)


async def run_profile_cleanup(
    profile_id: int,
    capture_retention_days: int,
    timelapse_retention_days: int,
) -> dict:
    """Run cleanup for a specific profile with given retention settings."""
    db = SessionLocal()
    summary = {
        "profile_id": profile_id,
        "captures_deleted": 0,
        "timelapses_deleted": 0,
        "orphan_records_cleaned": 0,
        "empty_dirs_removed": 0,
    }

    try:
        now = datetime.now(UTC)

        # 1. Delete old captures for this profile
        cutoff = now - timedelta(days=capture_retention_days)
        old_captures = db.execute(
            select(Capture).where(
                Capture.profile_id == profile_id,
                Capture.captured_at < cutoff,
            )
        ).scalars().all()

        for cap in old_captures:
            cap_abs = os.path.join(settings.DATA_DIR, cap.file_path)
            if os.path.exists(cap_abs):
                os.unlink(cap_abs)
            db.delete(cap)
            summary["captures_deleted"] += 1

        # 2. Delete old timelapses for this profile (all period types)
        cutoff = now - timedelta(days=timelapse_retention_days)
        old_tl = db.execute(
            select(Timelapse).where(
                Timelapse.profile_id == profile_id,
                Timelapse.created_at < cutoff,
            )
        ).scalars().all()

        for tl in old_tl:
            tl_abs = tl.file_path if os.path.isabs(tl.file_path) else os.path.join(settings.DATA_DIR, tl.file_path)
            if os.path.exists(tl_abs):
                os.unlink(tl_abs)
            db.delete(tl)
            summary["timelapses_deleted"] += 1

        db.commit()

        # 3. Clean orphaned DB records for this profile (file doesn't exist)
        profile_captures = db.execute(
            select(Capture).where(Capture.profile_id == profile_id)
        ).scalars().all()
        for cap in profile_captures:
            cap_abs = os.path.join(settings.DATA_DIR, cap.file_path)
            if not os.path.exists(cap_abs):
                db.delete(cap)
                summary["orphan_records_cleaned"] += 1

        profile_timelapses = db.execute(
            select(Timelapse).where(Timelapse.profile_id == profile_id)
        ).scalars().all()
        for tl in profile_timelapses:
            tl_abs = tl.file_path if os.path.isabs(tl.file_path) else os.path.join(settings.DATA_DIR, tl.file_path)
            if not os.path.exists(tl_abs):
                db.delete(tl)
                summary["orphan_records_cleaned"] += 1

        db.commit()

        # 4. Remove empty directories
        for base_name in ["captures", "timelapses"]:
            base_dir = os.path.join(settings.DATA_DIR, base_name)
            if not os.path.isdir(base_dir):
                continue
            for root, dirs, files in os.walk(base_dir, topdown=False):
                if root == base_dir:
                    continue
                if not os.listdir(root):
                    os.rmdir(root)
                    summary["empty_dirs_removed"] += 1

        logger.info("Profile cleanup complete: %s", summary)

        # Emit retention summary event
        try:
            from app.services.events import emit
            await emit(
                "retention_summary",
                "Cleanup complete",
                f"Profile {profile_id}: deleted {summary['captures_deleted']} captures, "
                f"{summary['timelapses_deleted']} timelapses. "
                f"Cleaned {summary['orphan_records_cleaned']} orphan records.",
            )
        except Exception:
            pass

        # Check low disk space
        try:
            usage = shutil.disk_usage(settings.DATA_DIR)
            free_pct = usage.free / usage.total * 100 if usage.total > 0 else 100
            threshold_db = SessionLocal()
            try:
                from app.models import Setting
                row = threshold_db.query(Setting).filter(Setting.key == "health_low_disk_threshold_percent").first()
                threshold = int(row.value) if row else 10
            finally:
                threshold_db.rollback()
                threshold_db.close()

            if free_pct < threshold:
                from app.services.events import emit
                await emit(
                    "low_disk_space",
                    "Low disk space warning",
                    f"Only {free_pct:.1f}% disk space remaining ({usage.free // (1024**3)} GB free of {usage.total // (1024**3)} GB).",
                    level="warning",
                )
        except Exception:
            pass

        return summary

    finally:
        db.rollback()
        db.close()


RECORDING_CLEANUP_BATCH_SIZE = 500


def _get_effective_retention(profile: Profile, db: Session) -> int:
    """Return effective recording retention days for a profile.

    Per-profile override takes precedence, then global setting, then default 14.
    """
    if profile.recording_retention_days and profile.recording_retention_days > 0:
        return profile.recording_retention_days
    row = db.query(Setting).filter(Setting.key == "default_recording_retention_days").first()
    return int(row.value) if row else 14


async def run_recording_cleanup(profile_id: int, retention_days: int) -> dict:
    """Delete expired, unprotected recording segments for a profile."""
    db = SessionLocal()
    summary = {
        "profile_id": profile_id,
        "segments_deleted": 0,
        "orphan_records_cleaned": 0,
        "empty_dirs_removed": 0,
    }

    try:
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=retention_days)

        expired_ids = (
            db.execute(
                select(RecordingSegment.id).where(
                    RecordingSegment.profile_id == profile_id,
                    RecordingSegment.start_time < cutoff,
                    RecordingSegment.protected == False,  # noqa: E712
                )
            )
            .scalars()
            .all()
        )

        for i in range(0, len(expired_ids), RECORDING_CLEANUP_BATCH_SIZE):
            batch = expired_ids[i : i + RECORDING_CLEANUP_BATCH_SIZE]
            segments = (
                db.execute(
                    select(RecordingSegment).where(RecordingSegment.id.in_(batch))
                )
                .scalars()
                .all()
            )
            for seg in segments:
                abs_path = os.path.join(settings.DATA_DIR, seg.file_path)
                try:
                    if os.path.exists(abs_path):
                        os.unlink(abs_path)
                except OSError:
                    logger.warning("Failed to delete segment file: %s", abs_path)
                db.delete(seg)
                summary["segments_deleted"] += 1
            db.commit()

        remaining = (
            db.execute(
                select(RecordingSegment).where(
                    RecordingSegment.profile_id == profile_id
                )
            )
            .scalars()
            .all()
        )
        for seg in remaining:
            abs_path = os.path.join(settings.DATA_DIR, seg.file_path)
            if not os.path.exists(abs_path):
                db.delete(seg)
                summary["orphan_records_cleaned"] += 1
        db.commit()

        rec_dir = recording_dir(profile) if (profile := db.get(Profile, profile_id)) else os.path.join(settings.DATA_DIR, "recordings", str(profile_id))
        if os.path.isdir(rec_dir):
            for root, dirs, files in os.walk(rec_dir, topdown=False):
                if root == rec_dir:
                    continue
                if not os.listdir(root):
                    os.rmdir(root)
                    summary["empty_dirs_removed"] += 1

        logger.info("Recording cleanup complete: %s", summary)

        try:
            from app.services.events import emit

            await emit(
                "recording_retention_summary",
                "Recording cleanup complete",
                f"Profile {profile_id}: deleted {summary['segments_deleted']} segments. "
                f"Cleaned {summary['orphan_records_cleaned']} orphan records.",
            )
        except Exception:
            pass

        return summary

    finally:
        db.rollback()
        db.close()


async def run_emergency_recording_cleanup(target_pct: float = 80) -> dict:
    """Delete oldest unprotected segments across all profiles until disk below target_pct."""
    summary = {"segments_deleted": 0, "freed_bytes": 0}
    db = SessionLocal()

    try:
        while True:
            usage = shutil.disk_usage(settings.DATA_DIR)
            used_pct = (usage.used / usage.total) * 100 if usage.total > 0 else 0
            if used_pct <= target_pct:
                break

            oldest = (
                db.execute(
                    select(RecordingSegment)
                    .where(RecordingSegment.protected == False)  # noqa: E712
                    .order_by(RecordingSegment.start_time.asc())
                    .limit(RECORDING_CLEANUP_BATCH_SIZE)
                )
                .scalars()
                .all()
            )

            if not oldest:
                logger.warning("Emergency cleanup: no unprotected segments left")
                try:
                    from app.services.events import emit

                    await emit(
                        "low_disk_space",
                        "Critical: disk full, no unprotected segments",
                        f"Disk at {used_pct:.1f}% — all remaining segments are protected.",
                        level="critical",
                    )
                except Exception:
                    pass
                break

            for seg in oldest:
                abs_path = os.path.join(settings.DATA_DIR, seg.file_path)
                file_size = seg.file_size or 0
                try:
                    if os.path.exists(abs_path):
                        os.unlink(abs_path)
                except OSError:
                    logger.warning("Failed to delete segment file: %s", abs_path)
                db.delete(seg)
                summary["segments_deleted"] += 1
                summary["freed_bytes"] += file_size
            db.commit()

        logger.info("Emergency recording cleanup complete: %s", summary)
        return summary

    finally:
        db.rollback()
        db.close()


def get_recording_storage_stats() -> dict:
    """Return total and per-profile recording storage breakdown."""
    db = SessionLocal()
    try:
        total = db.query(
            func.count(RecordingSegment.id),
            func.coalesce(func.sum(RecordingSegment.file_size), 0),
        ).first()

        per_profile = (
            db.query(
                RecordingSegment.profile_id,
                func.count(RecordingSegment.id).label("segment_count"),
                func.coalesce(func.sum(RecordingSegment.file_size), 0).label("total_bytes"),
                func.min(RecordingSegment.start_time).label("oldest"),
                func.max(RecordingSegment.start_time).label("newest"),
                func.sum(case((RecordingSegment.protected == True, 1), else_=0)).label("protected_count"),  # noqa: E712
            )
            .group_by(RecordingSegment.profile_id)
            .all()
        )

        profiles = []
        for row in per_profile:
            profiles.append(
                {
                    "profile_id": row.profile_id,
                    "segment_count": row.segment_count,
                    "total_bytes": row.total_bytes,
                    "protected_count": row.protected_count,
                    "oldest_recording": row.oldest.isoformat() if row.oldest else None,
                    "newest_recording": row.newest.isoformat() if row.newest else None,
                }
            )

        return {
            "total_segments": total[0],
            "total_bytes": total[1],
            "profiles": profiles,
        }
    finally:
        db.rollback()
        db.close()


def get_storage_stats() -> dict:
    """Calculate storage usage statistics."""
    db = SessionLocal()
    try:
        from sqlalchemy import func

        cap_stats = db.query(
            func.count(Capture.id),
            func.coalesce(func.sum(Capture.file_size), 0),
        ).first()
        captures_count = cap_stats[0]
        captures_size = cap_stats[1]

        tl_stats = db.query(
            func.count(Timelapse.id),
            func.coalesce(func.sum(Timelapse.file_size), 0),
        ).first()
        timelapses_count = tl_stats[0]
        timelapses_size = tl_stats[1]

        rec_stats = db.query(
            func.count(RecordingSegment.id),
            func.coalesce(func.sum(RecordingSegment.file_size), 0),
        ).first()
        recordings_count = rec_stats[0]
        recordings_size = rec_stats[1]

        from app.models import ClipExport
        exp_stats = db.query(
            func.count(ClipExport.id),
            func.coalesce(func.sum(ClipExport.file_size), 0),
        ).filter(ClipExport.status == "complete").first()
        exports_count = exp_stats[0]
        exports_size = exp_stats[1]

        total_size = captures_size + timelapses_size + recordings_size + exports_size

        # Disk usage
        try:
            usage = shutil.disk_usage(settings.DATA_DIR)
            disk_free = usage.free
            disk_total = usage.total
        except OSError:
            disk_free = 0
            disk_total = 0

        return {
            "captures_count": captures_count,
            "captures_size_bytes": captures_size,
            "timelapses_count": timelapses_count,
            "timelapses_size_bytes": timelapses_size,
            "recordings_count": recordings_count,
            "recordings_size_bytes": recordings_size,
            "exports_count": exports_count,
            "exports_size_bytes": exports_size,
            "total_size_bytes": total_size,
            "disk_free_bytes": disk_free,
            "disk_total_bytes": disk_total,
        }
    finally:
        db.rollback()
        db.close()
