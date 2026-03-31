"""Live HLS transcoding service — FFmpeg RTSP → HLS for real-time viewing."""

import asyncio
import logging
import os
import shutil
import time
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger(__name__)

# How long (seconds) an idle HLS session lives before being reaped
SESSION_TTL = 60
# How long (seconds) to wait before considering FFmpeg startup failed
STARTUP_TIMEOUT = 15
# HLS segment duration in seconds
SEGMENT_DURATION = 2
# Number of segments to keep in the playlist
HLS_LIST_SIZE = 5


@dataclass
class LiveSession:
    stream_id: int
    rtsp_url: str
    output_dir: str
    process: asyncio.subprocess.Process | None = None
    last_accessed: float = field(default_factory=time.monotonic)
    ready: bool = False
    _ready_event: asyncio.Event = field(default_factory=asyncio.Event)


class LiveHLSManager:
    def __init__(self) -> None:
        self._sessions: dict[int, LiveSession] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._reaper_task: asyncio.Task | None = None

    def _lock_for(self, stream_id: int) -> asyncio.Lock:
        if stream_id not in self._locks:
            self._locks[stream_id] = asyncio.Lock()
        return self._locks[stream_id]

    async def get_playlist_url(self, stream_id: int, rtsp_url: str) -> str:
        """Ensure a live HLS session is running and return the playlist path."""
        async with self._lock_for(stream_id):
            session = self._sessions.get(stream_id)
            if session is None or (session.process and session.process.returncode is not None):
                session = await self._start_session(stream_id, rtsp_url)
                self._sessions[stream_id] = session
            else:
                session.last_accessed = time.monotonic()

        # Wait for the first segment to appear (up to STARTUP_TIMEOUT)
        try:
            await asyncio.wait_for(session._ready_event.wait(), timeout=STARTUP_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("Live HLS session for stream %d did not become ready in time", stream_id)

        return f"/api/streams/{stream_id}/live-hls/playlist.m3u8"

    async def _start_session(self, stream_id: int, rtsp_url: str) -> LiveSession:
        output_dir = os.path.join(settings.DATA_DIR, "live", str(stream_id))
        os.makedirs(output_dir, exist_ok=True)

        # Clean up any stale segments from a previous session
        for f in os.listdir(output_dir):
            try:
                os.remove(os.path.join(output_dir, f))
            except OSError:
                pass

        session = LiveSession(stream_id=stream_id, rtsp_url=rtsp_url, output_dir=output_dir)

        playlist = os.path.join(output_dir, "playlist.m3u8")
        segment_pattern = os.path.join(output_dir, "seg%03d.ts")

        args = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            "-rtsp_transport", "tcp",
            "-stimeout", "5000000",
            "-i", rtsp_url,
            "-c:v", "copy",
            "-an",                          # drop audio — live preview doesn't need it
            "-f", "hls",
            "-hls_time", str(SEGMENT_DURATION),
            "-hls_list_size", str(HLS_LIST_SIZE),
            "-hls_flags", "delete_segments+omit_endlist",
            "-hls_segment_filename", segment_pattern,
            playlist,
        ]

        logger.info("Starting live HLS for stream %d", stream_id)
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        session.process = process

        # Background task: watch for first segment then log stderr
        asyncio.create_task(self._watch_session(session))

        # Ensure reaper is running
        if self._reaper_task is None or self._reaper_task.done():
            self._reaper_task = asyncio.create_task(self._reaper())

        return session

    async def _watch_session(self, session: LiveSession) -> None:
        """Poll for the playlist file and log FFmpeg stderr."""
        process = session.process
        assert process is not None

        # Poll until playlist appears or process dies
        while not session.ready:
            if os.path.exists(os.path.join(session.output_dir, "playlist.m3u8")):
                # Check the playlist has at least one segment line
                try:
                    with open(os.path.join(session.output_dir, "playlist.m3u8")) as f:
                        if any(line.strip().endswith(".ts") for line in f):
                            session.ready = True
                            session._ready_event.set()
                            logger.info("Live HLS stream %d is ready", session.stream_id)
                            break
                except OSError:
                    pass
            if process.returncode is not None:
                break
            await asyncio.sleep(0.5)

        # Drain stderr for diagnostics
        if process.stderr:
            try:
                stderr = await process.stderr.read()
                if stderr.strip():
                    logger.error("Live HLS FFmpeg stderr (stream %d): %s", session.stream_id,
                                 stderr.decode("utf-8", errors="replace").strip())
            except Exception:
                pass

    async def stop(self, stream_id: int) -> None:
        async with self._lock_for(stream_id):
            session = self._sessions.pop(stream_id, None)
            if session and session.process and session.process.returncode is None:
                session.process.terminate()
                try:
                    await asyncio.wait_for(session.process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    session.process.kill()
            output_dir = os.path.join(settings.DATA_DIR, "live", str(stream_id))
            if os.path.isdir(output_dir):
                shutil.rmtree(output_dir, ignore_errors=True)

    async def _reaper(self) -> None:
        """Periodically stop sessions that haven't been accessed recently."""
        while self._sessions:
            await asyncio.sleep(10)
            now = time.monotonic()
            stale = [
                sid for sid, s in self._sessions.items()
                if now - s.last_accessed > SESSION_TTL
            ]
            for sid in stale:
                logger.info("Reaping idle live HLS session for stream %d", sid)
                await self.stop(sid)

    def touch(self, stream_id: int) -> None:
        """Refresh TTL for a session (called when segments are served)."""
        if stream_id in self._sessions:
            self._sessions[stream_id].last_accessed = time.monotonic()


live_hls_manager = LiveHLSManager()
