"""Independent async export queue for clip export processing."""

import asyncio
import logging
import threading

from app.database import SessionLocal
from app.models import ClipExport

logger = logging.getLogger(__name__)

_export_queue: asyncio.Queue = asyncio.Queue()
_pending_exports: list[dict] = []
_pending_lock = threading.Lock()
_current_export: dict | None = None
_worker_task: asyncio.Task | None = None

_cancel_events: dict[int, threading.Event] = {}
_active_ffmpeg_proc: asyncio.subprocess.Process | None = None
_ffmpeg_lock = threading.Lock()


def set_active_ffmpeg_proc(proc: asyncio.subprocess.Process | None) -> None:
    global _active_ffmpeg_proc
    with _ffmpeg_lock:
        _active_ffmpeg_proc = proc


def get_active_ffmpeg_proc() -> asyncio.subprocess.Process | None:
    with _ffmpeg_lock:
        return _active_ffmpeg_proc


async def enqueue_export(clip_export_id: int) -> dict:
    cancel_event = threading.Event()
    _cancel_events[clip_export_id] = cancel_event

    with _pending_lock:
        _pending_exports.append({"clip_export_id": clip_export_id})
        position = len(_pending_exports)

    await _export_queue.put({"clip_export_id": clip_export_id})

    logger.info("Enqueued export %d at position %d", clip_export_id, position)
    return {"clip_export_id": clip_export_id, "position": position}


def cancel_export(clip_export_id: int) -> bool:
    global _current_export

    with _pending_lock:
        found_pending = any(
            j["clip_export_id"] == clip_export_id for j in _pending_exports
        )
        if found_pending:
            _pending_exports[:] = [
                j for j in _pending_exports
                if j["clip_export_id"] != clip_export_id
            ]

    if found_pending:
        event = _cancel_events.get(clip_export_id)
        if event:
            event.set()

        items = []
        while not _export_queue.empty():
            try:
                items.append(_export_queue.get_nowait())
                _export_queue.task_done()
            except asyncio.QueueEmpty:
                break
        for item in items:
            if item["clip_export_id"] != clip_export_id:
                _export_queue.put_nowait(item)

        _cancel_events.pop(clip_export_id, None)

        db = SessionLocal()
        try:
            export = db.query(ClipExport).get(clip_export_id)
            if export:
                export.status = "cancelled"
                db.commit()
        finally:
            db.close()

        logger.info("Cancelled queued export %d", clip_export_id)
        return True

    if _current_export and _current_export["clip_export_id"] == clip_export_id:
        event = _cancel_events.get(clip_export_id)
        if event:
            event.set()
        proc = get_active_ffmpeg_proc()
        if proc:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        logger.info("Cancelling active export %d", clip_export_id)
        return True

    return False


async def _export_worker() -> None:
    global _current_export
    from app.services.clip_export import process_clip_export

    logger.info("Export queue worker started")
    while True:
        job = await _export_queue.get()
        clip_export_id = job["clip_export_id"]

        event = _cancel_events.get(clip_export_id)
        if event and event.is_set():
            _cancel_events.pop(clip_export_id, None)
            with _pending_lock:
                _pending_exports[:] = [
                    j for j in _pending_exports
                    if j["clip_export_id"] != clip_export_id
                ]
            _export_queue.task_done()
            continue

        _current_export = job

        with _pending_lock:
            _pending_exports[:] = [
                j for j in _pending_exports
                if j["clip_export_id"] != clip_export_id
            ]

        try:
            await process_clip_export(clip_export_id, cancel_event=event)
        except Exception:
            logger.exception("Export %d failed in worker", clip_export_id)
        finally:
            _current_export = None
            _cancel_events.pop(clip_export_id, None)
            set_active_ffmpeg_proc(None)
            _export_queue.task_done()


def start_export_worker() -> None:
    global _worker_task
    _worker_task = asyncio.get_event_loop().create_task(_export_worker())
    logger.info("Export queue worker launched")


async def restore_pending_exports() -> None:
    db = SessionLocal()
    try:
        pending = (
            db.query(ClipExport)
            .filter(ClipExport.status.in_(["pending", "processing"]))
            .order_by(ClipExport.created_at.asc())
            .all()
        )

        for export in pending:
            if export.status == "processing":
                export.status = "pending"
            db.commit()

        for export in pending:
            await enqueue_export(export.id)

        if pending:
            logger.info("Restored %d pending exports", len(pending))
    finally:
        db.close()
