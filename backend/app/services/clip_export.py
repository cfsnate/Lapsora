"""Clip export service: FFmpeg-based clip extraction from recording segments."""

import asyncio
import logging
import os
import tempfile
import threading
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.database import SessionLocal
from app.models import ClipExport, RecordingSegment
from app.services.events import emit

logger = logging.getLogger(__name__)

CRF_MAP = {"high": 18, "medium": 23, "low": 28}
RESOLUTION_MAP = {"1080p": 1080, "720p": 720, "480p": 480}


class ExportCancelled(Exception):
    pass


async def process_clip_export(
    clip_export_id: int, cancel_event: threading.Event | None = None
) -> None:
    db = SessionLocal()
    concat_path: str | None = None
    try:
        export = db.query(ClipExport).get(clip_export_id)
        if not export:
            logger.error("ClipExport %d not found", clip_export_id)
            return

        export.status = "processing"
        db.commit()

        if cancel_event and cancel_event.is_set():
            raise ExportCancelled()

        segments = (
            db.query(RecordingSegment)
            .filter(
                RecordingSegment.profile_id == export.profile_id,
                RecordingSegment.start_time < export.end_time,
            )
            .order_by(RecordingSegment.start_time.asc())
            .all()
        )

        segments = [
            s for s in segments
            if s.start_time + timedelta(seconds=s.duration_seconds or 0) > export.start_time
        ]

        if not segments:
            export.status = "failed"
            export.error_message = "No recording segments found for the requested time range"
            db.commit()
            
            # Emit failure event for missing segments
            await emit(
                "clip_export_failed",
                f"Clip Export Failed",
                f"Clip export {export.id} failed: No recording segments found for the requested time range",
                "error",
                {"profile_id": export.profile_id, "export_id": export.id}
            )
            return

        export_dir = os.path.join(
            settings.DATA_DIR, "exports", str(export.profile_id)
        )
        os.makedirs(export_dir, exist_ok=True)

        fd, concat_path = tempfile.mkstemp(suffix=".txt", prefix="concat_")
        with os.fdopen(fd, "w") as f:
            for seg in segments:
                abs_path = os.path.join(settings.DATA_DIR, seg.file_path)
                f.write(f"file '{abs_path}'\n")

        offset = max(
            (export.start_time - segments[0].start_time).total_seconds(), 0
        )
        duration = (export.end_time - export.start_time).total_seconds()

        output_filename = f"clip_{export.id}_{int(datetime.now(UTC).timestamp())}.mp4"
        output_path = os.path.join(export_dir, output_filename)

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", concat_path,
            "-ss", str(offset),
            "-t", str(duration),
        ]

        if export.quality_preset == "original":
            cmd.extend(["-c", "copy"])
        else:
            crf = CRF_MAP.get(export.quality_preset, 23)
            cmd.extend([
                "-c:v", "libx264",
                "-crf", str(crf),
                "-preset", "medium",
                "-pix_fmt", "yuv420p",
            ])
            height = RESOLUTION_MAP.get(export.resolution)
            if height and export.resolution != "original":
                cmd.extend(["-vf", f"scale=-2:{height}"])

        cmd.extend(["-movflags", "+faststart", output_path])

        if cancel_event and cancel_event.is_set():
            raise ExportCancelled()

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        from app.services.export_queue import set_active_ffmpeg_proc
        set_active_ffmpeg_proc(proc)

        stdout, stderr = await proc.communicate()

        if cancel_event and cancel_event.is_set():
            raise ExportCancelled()

        if proc.returncode == 0:
            rel_path = os.path.join(
                "exports", str(export.profile_id), output_filename
            )
            export.file_path = rel_path
            export.file_size = os.path.getsize(output_path)
            export.duration_seconds = duration
            export.status = "completed"
            export.completed_at = datetime.now(UTC)
            
            # Emit completion event
            await emit(
                "clip_export_complete",
                f"Clip Export Complete",
                f"Clip export {export.id} completed successfully. Duration: {duration:.1f}s, Quality: {export.quality_preset}",
                "info",
                {"profile_id": export.profile_id, "export_id": export.id}
            )
        else:
            export.status = "failed"
            export.error_message = stderr.decode(errors="replace")[:1000]
            
            # Emit failure event
            await emit(
                "clip_export_failed",
                f"Clip Export Failed",
                f"Clip export {export.id} failed: {export.error_message}",
                "error",
                {"profile_id": export.profile_id, "export_id": export.id}
            )

        db.commit()

    except ExportCancelled:
        logger.info("Export %d cancelled", clip_export_id)
        export = db.query(ClipExport).get(clip_export_id)
        if export and export.status == "processing":
            export.status = "cancelled"
            db.commit()
    except Exception:
        logger.exception("Export %d failed unexpectedly", clip_export_id)
        try:
            export = db.query(ClipExport).get(clip_export_id)
            if export:
                export.status = "failed"
                export.error_message = "Unexpected processing error"
                db.commit()
                
                # Emit failure event for unexpected error
                await emit(
                    "clip_export_failed",
                    f"Clip Export Failed",
                    f"Clip export {export.id} failed unexpectedly",
                    "error",
                    {"profile_id": export.profile_id, "export_id": export.id}
                )
        except Exception:
            logger.exception("Failed to update export status after error")
    finally:
        if concat_path and os.path.exists(concat_path):
            os.unlink(concat_path)
        from app.services.export_queue import set_active_ffmpeg_proc
        set_active_ffmpeg_proc(None)
        db.close()
