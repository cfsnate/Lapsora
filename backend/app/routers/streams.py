"""Stream management endpoints."""

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.config import decrypt, encrypt, settings
from app.database import get_db
from app.models import Setting, Stream
from app.schemas import StreamCreate, StreamRead, StreamUpdate
from app.services import rtsp
from app.services import go2rtc
from app.services.live_hls import live_hls_manager

router = APIRouter(prefix="/api/streams", tags=["streams"])


@router.get("/", response_model=list[StreamRead])
def list_streams(db: Session = Depends(get_db)):
    return db.query(Stream).order_by(Stream.id).all()


@router.get("/go2rtc/discover")
async def discover_go2rtc_streams(db: Session = Depends(get_db)):
    base_url = go2rtc.get_go2rtc_url(db)
    if not base_url:
        raise HTTPException(400, "go2rtc URL not configured")
    try:
        return await go2rtc.list_streams(base_url)
    except Exception as exc:
        raise HTTPException(502, f"Failed to fetch go2rtc streams: {exc}")


@router.post("/", response_model=StreamRead, status_code=201)
def create_stream(body: StreamCreate, db: Session = Depends(get_db)):
    if body.source_type == "go2rtc":
        if not body.go2rtc_name:
            raise HTTPException(400, "go2rtc_name is required for go2rtc streams")
        stream = Stream(
            name=body.name,
            url=encrypt(""),
            source_type="go2rtc",
            go2rtc_name=body.go2rtc_name,
        )
    else:
        if not body.url:
            raise HTTPException(400, "url is required for RTSP streams")
        stream = Stream(name=body.name, url=encrypt(body.url), source_type="rtsp")
    db.add(stream)
    db.commit()
    db.refresh(stream)
    return stream


@router.get("/{stream_id}", response_model=StreamRead)
def get_stream(stream_id: int, db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")
    return stream


@router.put("/{stream_id}", response_model=StreamRead)
def update_stream(stream_id: int, body: StreamUpdate, db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    if body.name is not None:
        stream.name = body.name
    if body.url is not None:
        stream.url = encrypt(body.url)
    if body.enabled is not None:
        stream.enabled = body.enabled

    db.commit()
    db.refresh(stream)
    return stream


@router.delete("/{stream_id}", status_code=204)
def delete_stream(stream_id: int, db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    # Remove scheduler jobs for all profiles before cascade delete
    from app.services.scheduler import remove_capture_job
    for profile in stream.profiles:
        remove_capture_job(profile.id)

    db.delete(stream)
    db.commit()


@router.post("/{stream_id}/test")
async def test_stream(stream_id: int, db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    if stream.source_type == "go2rtc":
        base_url = go2rtc.get_go2rtc_url(db)
        if not base_url:
            raise HTTPException(400, "go2rtc URL not configured")
        return await go2rtc.test_stream(base_url, stream.go2rtc_name)

    try:
        url = decrypt(stream.url)
    except (InvalidToken, Exception):
        raise HTTPException(400, "Stream URL could not be decrypted. Please re-enter the RTSP URL.")
    return await rtsp.test_connection(url)


@router.get("/{stream_id}/preview")
async def preview_stream(stream_id: int, db: Session = Depends(get_db)):
    import os
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    # Serve cached preview thumbnail if available (updated by capture jobs)
    preview_path = os.path.join(settings.DATA_DIR, "previews", f"{stream_id}.jpg")
    if os.path.isfile(preview_path):
        return FileResponse(
            preview_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=30"},
        )

    # Fallback: live grab (slow, spawns FFmpeg)
    if stream.source_type == "go2rtc":
        base_url = go2rtc.get_go2rtc_url(db)
        if not base_url:
            raise HTTPException(400, "go2rtc URL not configured")
        try:
            jpeg_bytes = await go2rtc.grab_frame(base_url, stream.go2rtc_name)
        except Exception as exc:
            raise HTTPException(502, str(exc))
        return Response(content=jpeg_bytes, media_type="image/jpeg")

    try:
        url = decrypt(stream.url)
    except (InvalidToken, Exception):
        raise HTTPException(400, "Stream URL could not be decrypted. Please re-enter the RTSP URL.")
    try:
        jpeg_bytes = await rtsp.grab_frame(url)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))
    return Response(content=jpeg_bytes, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=30"})

@router.get("/{stream_id}/live-url")
async def get_live_url(stream_id: int, db: Session = Depends(get_db)):
    stream = db.get(Stream, stream_id)
    if not stream:
        raise HTTPException(404, "Stream not found")

    if stream.source_type == "go2rtc":
        base_url = go2rtc.get_go2rtc_url(db)
        if not base_url:
            raise HTTPException(400, "go2rtc URL not configured")
        ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://")
        return {"ws_url": f"{ws_url}/api/ws?src={stream.go2rtc_name}", "hls_url": None}

    # Native RTSP — transcode to HLS via FFmpeg
    try:
        rtsp_url = decrypt(stream.url)
    except (InvalidToken, Exception):
        raise HTTPException(400, "Stream URL could not be decrypted. Please re-enter the RTSP URL.")

    try:
        hls_path = await live_hls_manager.get_playlist_url(stream_id, rtsp_url)
    except Exception as exc:
        raise HTTPException(502, f"Failed to start live stream: {exc}")

    return {"ws_url": None, "hls_url": hls_path}


@router.get("/{stream_id}/live-hls/{filename}")
async def serve_live_hls(stream_id: int, filename: str):
    """Serve live HLS playlist and segment files."""
    import os
    if ".." in filename or "/" in filename:
        raise HTTPException(400, "Invalid filename")

    live_hls_manager.touch(stream_id)

    file_path = os.path.join(settings.DATA_DIR, "live", str(stream_id), filename)

    if filename.endswith(".m3u8"):
        if not os.path.exists(file_path):
            # FFmpeg hasn't written the playlist yet — return a valid empty live
            # playlist so HLS.js keeps polling rather than fataling on 404.
            empty_playlist = (
                "#EXTM3U\n"
                "#EXT-X-VERSION:3\n"
                f"#EXT-X-TARGETDURATION:{2}\n"
                "#EXT-X-MEDIA-SEQUENCE:0\n"
            )
            return Response(
                content=empty_playlist.encode(),
                media_type="application/vnd.apple.mpegurl",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except OSError:
            raise HTTPException(404, "File not found")
        return Response(
            content=content,
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
        )
    elif filename.endswith(".ts"):
        if not os.path.exists(file_path):
            raise HTTPException(404, "File not found")
        return FileResponse(
            file_path,
            media_type="video/mp2t",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    raise HTTPException(400, "Unknown file type")
