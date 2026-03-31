"""Clip export API: create, list, download, cancel, and delete exports."""

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import ClipExport
from app.schemas import ClipExportCreate, ClipExportRead
from app.services.export_queue import cancel_export, enqueue_export

router = APIRouter(prefix="/api/exports", tags=["exports"])


@router.post("/", status_code=202)
async def create_export(body: ClipExportCreate, db: Session = Depends(get_db)):
    clip_export = ClipExport(
        profile_id=body.profile_id,
        start_time=body.start_time,
        end_time=body.end_time,
        quality_preset=body.quality_preset,
        resolution=body.resolution,
        status="pending",
    )
    db.add(clip_export)
    db.commit()
    db.refresh(clip_export)

    result = await enqueue_export(clip_export.id)
    return {"status": "queued", "id": clip_export.id, **result}


def _export_with_names(export: ClipExport) -> dict:
    """Add profile_name and stream_name to an export for serialization."""
    d = {c.name: getattr(export, c.name) for c in export.__table__.columns}
    d["profile_name"] = export.profile.name if export.profile else None
    d["stream_name"] = export.profile.stream.name if export.profile and export.profile.stream else None
    return d


@router.get("/", response_model=list[ClipExportRead])
def list_exports(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(ClipExport).order_by(ClipExport.created_at.desc())
    if status is not None:
        stmt = stmt.where(ClipExport.status == status)
    exports = db.execute(stmt).scalars().all()
    return [_export_with_names(e) for e in exports]


@router.get("/{export_id}", response_model=ClipExportRead)
def get_export(export_id: int, db: Session = Depends(get_db)):
    export = db.get(ClipExport, export_id)
    if not export:
        raise HTTPException(status_code=404, detail="Export not found")
    return _export_with_names(export)


@router.get("/{export_id}/download")
def download_export(export_id: int, db: Session = Depends(get_db)):
    export = db.get(ClipExport, export_id)
    if not export:
        raise HTTPException(status_code=404, detail="Export not found")
    if export.status != "completed" or not export.file_path:
        raise HTTPException(status_code=404, detail="Export not ready for download")

    abs_path = os.path.join(settings.DATA_DIR, export.file_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Export file not found on disk")

    return FileResponse(
        abs_path,
        media_type="video/mp4",
        filename=os.path.basename(export.file_path),
    )


@router.delete("/{export_id}/cancel")
def cancel_export_endpoint(export_id: int, db: Session = Depends(get_db)):
    export = db.get(ClipExport, export_id)
    if not export:
        raise HTTPException(status_code=404, detail="Export not found")
    if export.status not in ("pending", "processing"):
        raise HTTPException(status_code=404, detail="Export cannot be cancelled")

    cancel_export(export_id)
    export.status = "cancelled"
    db.commit()
    return {"status": "cancelled", "id": export_id}


@router.delete("/{export_id}", status_code=204)
def delete_export(export_id: int, db: Session = Depends(get_db)):
    export = db.get(ClipExport, export_id)
    if not export:
        raise HTTPException(status_code=404, detail="Export not found")

    if export.file_path:
        abs_path = os.path.join(settings.DATA_DIR, export.file_path)
        if os.path.isfile(abs_path):
            os.unlink(abs_path)

    db.delete(export)
    db.commit()
