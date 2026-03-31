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
        """Ensure a live HLS session is running and return the playlist path.

        Returns immediately — does not wait for FFmpeg to produce segments.
        HLS.js on the client handles polling until the stream is ready.
        """
        async with self._lock_for(stream_id):
            session = self._sessions.get(stream_id)
            if session is None or (session.process and session.process.returncode is not None):
                session = await self._start_session(stream_id, rtsp_url)
                self._sessions[stream_id] = session
            else:
                session.last_accessed = time.monotonic()

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
        """Log when the stream becomes ready and capture FFmpeg stderr on exit."""
        process = session.process
        assert process is not None

        # Poll until first segment exists — just for logging, not blocking the API
        while not session.ready:
            playlist_path = os.path.join(session.output_dir, "playlist.m3u8")
            if os.path.exists(playlist_path):
                try:
                    with open(playlist_path) as f:
                        lines = f.readlines()
                    ts_files = [l.strip() for l in lines if l.strip().endswith(".ts")]
                    if ts_files:
                        seg_path = os.path.join(session.output_dir, ts_files[-1])
                        if os.path.exists(seg_path) and os.path.getsize(seg_path) > 0:
                            session.ready = True
                            logger.info("Live HLS stream %d is ready (%d segments visible)",
                                        session.stream_id, len(ts_files))
                            break
                except OSError:
                    pass
            if process.returncode is not None:
                break
            await asyncio.sleep(0.25)

        if not session.ready:
            logger.error("Live HLS FFmpeg exited before stream became ready (stream %d)",
                         session.stream_id)

        # Wait for process to exit, then capture stderr for diagnostics
        try:
            await asyncio.wait_for(process.wait(), timeout=30)
        except asyncio.TimeoutError:
            pass

        if process.stderr:
            try:
                stderr = await asyncio.wait_for(process.stderr.read(), timeout=2.0)
                if stderr.strip():
                    logger.error("Live HLS FFmpeg stderr (stream %d): %s", session.stream_id,
                                 stderr.decode("utf-8", errors="replace").strip())
            except (asyncio.TimeoutError, Exception):
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
