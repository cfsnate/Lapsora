"""Recording engine — manages FFmpeg processes for continuous MPEG-TS recording."""

import asyncio
import json
import logging
import os
import re
import threading
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from app.config import decrypt, settings
from app.database import SessionLocal
from app.models import Profile, RecordingSegment, Setting, Stream
from app.services.events import emit
from app.services.go2rtc import get_go2rtc_url
from app.services.notifications import _sse_lock, sse_queues

logger = logging.getLogger(__name__)

GO2RTC_DEFAULT_RTSP_PORT = 8554
BACKOFF_SCHEDULE = [0, 5, 10, 30, 60]
MIN_SEGMENT_SIZE = 1024


def _slug(name: str) -> str:
    """Convert a name to a safe directory component (lowercase, hyphens, no special chars)."""
    name = name.strip().lower()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[\s_]+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name or "unnamed"


def recording_dir(profile: Profile) -> str:
    """Absolute output directory for a profile's recordings.

    Layout: data/recordings/<stream-slug>-<stream_id>/<profile-slug>-<profile_id>/
    IDs are appended so renames never cause collisions.
    """
    stream_slug = _slug(profile.stream.name) if profile.stream else "stream"
    profile_slug = _slug(profile.name)
    rel = os.path.join(
        "recordings",
        f"{stream_slug}-{profile.stream_id}",
        f"{profile_slug}-{profile.id}",
    )
    return os.path.join(settings.DATA_DIR, rel)


def recording_rel(profile: Profile, fname: str) -> str:
    """DB-relative file_path for a segment filename."""
    stream_slug = _slug(profile.stream.name) if profile.stream else "stream"
    profile_slug = _slug(profile.name)
    return os.path.join(
        "recordings",
        f"{stream_slug}-{profile.stream_id}",
        f"{profile_slug}-{profile.id}",
        fname,
    )


BACKOFF_SCHEDULE = [0, 5, 10, 30, 60]


def resolve_recording_url(stream: Stream, db) -> str:
    """Resolve the RTSP URL for recording from either go2rtc or direct RTSP source."""
    if stream.source_type == "go2rtc":
        base_url = get_go2rtc_url(db)
        if base_url is None:
            raise ValueError("go2rtc URL not configured")
        parsed = urlparse(base_url)
        host = parsed.hostname
        return f"rtsp://{host}:{GO2RTC_DEFAULT_RTSP_PORT}/{stream.go2rtc_name}"
    if stream.source_type == "rtsp":
        return decrypt(stream.url)
    raise ValueError(f"Unknown source_type: {stream.source_type}")


def _is_within_recording_window(profile: Profile, db, now: datetime) -> bool:
    """Check if the current time falls within the profile's recording window."""
    if profile.recording_mode == "always":
        return True

    if profile.recording_mode == "manual":
        return False

    if profile.recording_mode == "scheduled":
        if not profile.recording_start_time or not profile.recording_end_time:
            return True
        start = datetime.strptime(profile.recording_start_time, "%H:%M").time()
        end = datetime.strptime(profile.recording_end_time, "%H:%M").time()
        current = now.time()

        days_str = profile.recording_days.strip() if profile.recording_days else ""
        if days_str:
            allowed_days = {d.strip() for d in days_str.split(",") if d.strip()}
            if now.strftime("%a") not in allowed_days:
                return False

        if start <= end:
            return start <= current <= end
        return current >= start or current <= end

    if profile.recording_mode == "sun":
        try:
            from astral import LocationInfo
            from astral.sun import dawn, dusk, sun

            lat_row = db.query(Setting).filter(Setting.key == "location_latitude").first()
            lon_row = db.query(Setting).filter(Setting.key == "location_longitude").first()
            if not lat_row or not lon_row:
                return True
            lat, lon = float(lat_row.value), float(lon_row.value)
            loc = LocationInfo(latitude=lat, longitude=lon)
            s = sun(loc.observer, date=now.date())
            offset = timedelta(minutes=profile.recording_sun_offset_minutes)

            events = (
                set(e.strip() for e in profile.recording_sun_events.split(",") if e.strip())
                if profile.recording_sun_events
                else set()
            )
            if not events:
                events = {"daylight"}

            windows: list[tuple] = []
            sunrise = s["sunrise"]
            sunset = s["sunset"]

            try:
                civil_dawn = dawn(loc.observer, date=now.date(), depression=6)
                civil_dusk = dusk(loc.observer, date=now.date(), depression=6)
            except ValueError:
                civil_dawn = sunrise
                civil_dusk = sunset

            if "daylight" in events:
                windows.append(((sunrise - offset).time(), (sunset + offset).time()))
            if "golden_hour" in events:
                windows.append(((sunrise - offset).time(), (sunrise + timedelta(hours=1) + offset).time()))
                windows.append(((sunset - timedelta(hours=1) - offset).time(), (sunset + offset).time()))
            if "blue_hour" in events:
                windows.append(((civil_dawn - offset).time(), (sunrise + offset).time()))
                windows.append(((sunset - offset).time(), (civil_dusk + offset).time()))
            if "night" in events:
                windows.append(((civil_dusk - offset).time(), (civil_dawn + offset).time()))

            if not windows:
                return True

            current = now.time()
            for win_start, win_end in windows:
                if win_start <= win_end:
                    if win_start <= current <= win_end:
                        return True
                else:
                    if current >= win_start or current <= win_end:
                        return True
            return False

        except Exception:
            logger.warning("Failed to compute sun times for profile %d, allowing recording", profile.id)
            return True

    return False


class RecordingProcess:
    """Manages a single FFmpeg recording subprocess for one profile."""

    def __init__(self, profile_id: int, stream_id: int, rtsp_url: str, output_dir: str, segment_duration: int):
        self.profile_id = profile_id
        self.stream_id = stream_id
        self.rtsp_url = rtsp_url
        self.output_dir = output_dir
        self.segment_duration = segment_duration
        self.process: asyncio.subprocess.Process | None = None
        self.state: str = "stopped"
        self.started_at: datetime | None = None
        self.last_segment_at: datetime | None = None
        self.retry_count: int = 0
        self._watchdog_task: asyncio.Task | None = None
        self._wait_task: asyncio.Task | None = None

    def _build_ffmpeg_args(self) -> list[str]:
        os.makedirs(self.output_dir, exist_ok=True)
        pattern = os.path.join(self.output_dir, "%Y%m%d_%H%M%S.ts")
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "warning",
            "-rtsp_transport", "tcp",
            "-rtsp_flags", "prefer_tcp",
            "-use_wallclock_as_timestamps", "1",
            "-stimeout", "30000000",      # 30s RTSP socket I/O timeout (microseconds)
            "-i", self.rtsp_url,
            "-c", "copy",
            "-f", "segment",
            "-segment_time", str(self.segment_duration),
            "-segment_format", "mpegts",
            "-reset_timestamps", "1",
            "-strftime", "1",
            pattern,
        ]

    async def _start_ffmpeg(self) -> None:
        args = self._build_ffmpeg_args()
        logger.info("Starting FFmpeg for profile %d with command: %s", self.profile_id, ' '.join(args))
        
        self.process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self.state = "recording"
        self.started_at = datetime.now(UTC)
        self._watchdog_task = asyncio.create_task(self._watchdog())
        self._wait_task = asyncio.create_task(self._wait_for_exit())
        
        # Emit recording started event
        profile_title = f"Profile {self.profile_id}"
        await emit(
            "recording_started",
            f"Recording started for {profile_title}",
            f"FFmpeg recording process started for profile {self.profile_id} at {self.started_at.isoformat()}",
            "info",
            {"profile_id": self.profile_id, "stream_id": self.stream_id}
        )
        
        await self._emit_status_event()

    async def _stop_ffmpeg(self) -> None:
        self.state = "stopped"
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            self._watchdog_task = None
        if self.process is not None and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=10)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self._wait_task is not None:
            self._wait_task.cancel()
            self._wait_task = None
        
        # Emit recording stopped event
        profile_title = f"Profile {self.profile_id}"
        stopped_at = datetime.now(UTC)
        duration = (stopped_at - self.started_at).total_seconds() if self.started_at else 0
        await emit(
            "recording_stopped",
            f"Recording stopped for {profile_title}",
            f"FFmpeg recording process stopped for profile {self.profile_id} after {duration:.1f} seconds",
            "info",
            {"profile_id": self.profile_id, "stream_id": self.stream_id, "duration_seconds": duration}
        )
        
        await self._emit_status_event()

    async def _wait_for_exit(self) -> None:
        returncode = await self.process.wait()
        # Read stderr to get error details
        stderr_output = ""
        if self.process.stderr:
            try:
                stderr_data = await self.process.stderr.read()
                stderr_output = stderr_data.decode('utf-8', errors='replace').strip()
            except Exception as e:
                logger.warning("Failed to read FFmpeg stderr: %s", e)
        
        await self._on_process_exit(returncode, stderr_output)

    async def _on_process_exit(self, returncode: int, stderr_output: str = "") -> None:
        if self.state == "stopped":
            return
        self.state = "error"
        
        # Log stderr output for debugging
        if stderr_output:
            logger.error("FFmpeg stderr for profile %d: %s", self.profile_id, stderr_output)
        
        # Emit recording failed event
        profile_title = f"Profile {self.profile_id}"
        failed_at = datetime.now(UTC)
        duration = (failed_at - self.started_at).total_seconds() if self.started_at else 0
        
        # Include stderr in the notification body if available
        error_detail = f" Error: {stderr_output}" if stderr_output else ""
        notification_body = f"FFmpeg recording process failed for profile {self.profile_id} with exit code {returncode} after {duration:.1f} seconds. Retry attempt {self.retry_count + 1}.{error_detail}"
        
        await emit(
            "recording_failed",
            f"Recording failed for {profile_title}",
            notification_body,
            "error",
            {
                "profile_id": self.profile_id, 
                "stream_id": self.stream_id, 
                "exit_code": returncode,
                "duration_seconds": duration,
                "retry_count": self.retry_count + 1,
                "stderr": stderr_output
            }
        )
        
        await self._emit_status_event()
        delay = BACKOFF_SCHEDULE[min(self.retry_count, len(BACKOFF_SCHEDULE) - 1)]
        self.retry_count += 1
        logger.warning(
            "FFmpeg exited with code %d for profile %d, retrying in %ds (attempt %d)",
            returncode, self.profile_id, delay, self.retry_count,
        )
        await asyncio.sleep(delay)
        if self.state == "stopped":
            return
        await self._start_ffmpeg()

    async def _watchdog(self) -> None:
        while self.state == "recording":
            await asyncio.sleep(self.segment_duration)
            if self.last_segment_at is None:
                continue
            elapsed = (datetime.now(UTC) - self.last_segment_at).total_seconds()
            if elapsed > self.segment_duration * 2:
                logger.warning(
                    "Watchdog: no new segment for %.0fs (threshold %ds) on profile %d",
                    elapsed, self.segment_duration * 2, self.profile_id,
                )
                if self._wait_task is not None:
                    self._wait_task.cancel()
                    self._wait_task = None
                self.process.kill()
                await self.process.wait()
                self.state = "error"
                await self._emit_status_event()
                await self._start_ffmpeg()
                break

    def on_segment_produced(self) -> None:
        self.last_segment_at = datetime.now(UTC)
        self.retry_count = 0

    async def _emit_status_event(self) -> None:
        data = json.dumps({
            "event_type": "recording_status",
            "profile_id": self.profile_id,
            "state": self.state,
            "started_at": self.started_at.isoformat() if self.started_at else None,
        })
        with _sse_lock:
            queues = list(sse_queues)
        for q in queues:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                pass


class RecordingManager:
    """Singleton that owns all FFmpeg recording subprocesses."""

    def __init__(self) -> None:
        self._processes: dict[int, RecordingProcess] = {}

    async def start(self, profile_id: int) -> None:
        db = SessionLocal()
        try:
            profile = db.query(Profile).filter(Profile.id == profile_id).first()
            if profile is None:
                logger.warning("Profile %d not found, cannot start recording", profile_id)
                return
            if not profile.recording_enabled:
                logger.debug("Recording not enabled for profile %d", profile_id)
                return

            now = datetime.now(UTC)
            if not _is_within_recording_window(profile, db, now):
                logger.debug("Profile %d outside recording window, skipping", profile_id)
                return

            rtsp_url = resolve_recording_url(profile.stream, db)
            output_dir = recording_dir(profile)

            if profile_id in self._processes and self._processes[profile_id].state == "recording":
                await self._processes[profile_id]._stop_ffmpeg()

            rp = RecordingProcess(
                profile_id=profile_id,
                stream_id=profile.stream_id,
                rtsp_url=rtsp_url,
                output_dir=output_dir,
                segment_duration=profile.segment_duration_seconds,
            )
            self._processes[profile_id] = rp
            await rp._start_ffmpeg()
        except Exception:
            logger.exception("Failed to start recording for profile %d", profile_id)
            if profile_id in self._processes:
                self._processes[profile_id].state = "error"
        finally:
            db.close()

    async def stop(self, profile_id: int) -> None:
        if profile_id in self._processes:
            await self._processes[profile_id]._stop_ffmpeg()
            del self._processes[profile_id]

    async def stop_all(self) -> None:
        """Stop all active recording processes."""
        for pid in list(self._processes.keys()):
            await self.stop(pid)

    async def start_all(self) -> None:
        """Start recording for all enabled profiles."""
        db = SessionLocal()
        try:
            profiles = db.query(Profile).filter(
                Profile.recording_enabled.is_(True)
            ).all()
            for p in profiles:
                await self.start(p.id)
        finally:
            db.close()

    async def restart(self, profile_id: int) -> None:
        await self.stop(profile_id)
        await self.start(profile_id)

    def get_status(self, profile_id: int) -> dict:
        if profile_id in self._processes:
            rp = self._processes[profile_id]
            return {
                "state": rp.state,
                "started_at": rp.started_at.isoformat() if rp.started_at else None,
                "last_segment_at": rp.last_segment_at.isoformat() if rp.last_segment_at else None,
                "retry_count": rp.retry_count,
            }
        return {"state": "stopped", "started_at": None, "last_segment_at": None, "retry_count": 0}

    def get_all_statuses(self) -> dict[int, dict]:
        return {pid: self.get_status(pid) for pid in self._processes}

    async def restore_all(self) -> None:
        db = SessionLocal()
        try:
            profiles = db.query(Profile).filter(Profile.recording_enabled.is_(True)).all()
            for profile in profiles:
                try:
                    await self.start(profile.id)
                except Exception:
                    logger.exception("Failed to restore recording for profile %d", profile.id)
        finally:
            db.close()

    async def shutdown(self) -> None:
        for profile_id in list(self._processes.keys()):
            try:
                await self.stop(profile_id)
            except Exception:
                logger.exception("Error stopping recording for profile %d during shutdown", profile_id)

    def on_segment_produced(self, profile_id: int) -> None:
        if profile_id in self._processes:
            self._processes[profile_id].on_segment_produced()


recording_manager = RecordingManager()


async def _get_segment_duration(path: str) -> float | None:
    """Get segment duration in seconds via ffprobe."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return float(stdout.decode().strip())
    except Exception:
        return None


def _parse_segment_timestamp(filename: str) -> datetime:
    """Extract datetime from segment filename pattern YYYYMMDD_HHMMSS.ts.

    FFmpeg's -strftime uses the system clock, which follows the container's
    timezone. Parse as local time and convert to UTC for consistent storage.
    """
    name = os.path.splitext(filename)[0]
    try:
        local_dt = datetime.strptime(name, "%Y%m%d_%H%M%S")
        return local_dt.astimezone(UTC)
    except ValueError:
        return datetime.now(UTC)


async def scan_segments() -> None:
    """Periodic job that discovers new .ts segment files and registers them in the database.

    Two-pass approach:
    1. New files above MIN_SEGMENT_SIZE are registered immediately — even while
       still being written — with duration_seconds=NULL so the timeline shows them.
    2. A segment is considered complete when a newer segment file exists in the same
       directory (meaning FFmpeg has moved on to writing the next segment). At that
       point we probe with ffprobe and fill in the real duration.
    """
    db = SessionLocal()
    try:
        profiles = db.query(Profile).filter(Profile.recording_enabled.is_(True)).all()

        for profile in profiles:
            output_dir = recording_dir(profile)
            if not os.path.isdir(output_dir):
                continue

            # Collect all .ts filenames sorted by name (= chronological)
            ts_files = sorted(
                f for f in os.listdir(output_dir) if f.endswith(".ts")
            )
            if not ts_files:
                continue

            # The last file in sorted order is the one currently being written
            latest_fname = ts_files[-1]

            # Map known segments by file_path for quick lookup + update
            existing = {
                seg.file_path: seg
                for seg in db.query(RecordingSegment)
                .filter(RecordingSegment.profile_id == profile.id)
                .all()
            }

            for fname in ts_files:
                fpath = os.path.join(output_dir, fname)
                rel_path = recording_rel(profile, fname)

                try:
                    stat = os.stat(fpath)
                except OSError:
                    continue
                if stat.st_size < MIN_SEGMENT_SIZE:
                    continue

                # A segment is complete once a newer file exists (FFmpeg moved on)
                is_complete = fname != latest_fname

                if rel_path not in existing:
                    # Register immediately — duration is NULL for in-progress segments
                    start_time = _parse_segment_timestamp(fname)
                    duration = await _get_segment_duration(fpath) if is_complete else None

                    segment = RecordingSegment(
                        profile_id=profile.id,
                        file_path=rel_path,
                        file_size=stat.st_size,
                        duration_seconds=duration,
                        start_time=start_time,
                        end_time=start_time + timedelta(seconds=duration) if duration else None,
                    )
                    db.add(segment)
                    recording_manager.on_segment_produced(profile.id)

                elif is_complete and existing[rel_path].duration_seconds is None:
                    # Backfill: segment is complete, probe real duration
                    seg = existing[rel_path]
                    duration = await _get_segment_duration(fpath)
                    if duration is not None:
                        seg.duration_seconds = duration
                        seg.end_time = seg.start_time + timedelta(seconds=duration)
                        seg.file_size = stat.st_size

        db.commit()
    except Exception:
        logger.exception("Segment scan failed")
        db.rollback()
    finally:
        db.close()
