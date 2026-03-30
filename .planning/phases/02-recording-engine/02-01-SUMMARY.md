---
phase: 02-recording-engine
plan: 01
subsystem: recording
tags: [ffmpeg, rtsp, mpeg-ts, asyncio, subprocess, sse]

requires:
  - phase: 01-data-model-recording-configuration
    provides: "Profile recording columns (recording_enabled, recording_mode, segment_duration_seconds, etc.), RecordingSegment model"
provides:
  - "RecordingManager singleton for FFmpeg process lifecycle"
  - "RecordingProcess class with start/stop/restart/watchdog/backoff"
  - "resolve_recording_url for go2rtc and direct RTSP sources"
  - "_is_within_recording_window for always/scheduled/sun/manual modes"
  - "scan_segments periodic job for registering .ts files in DB"
  - "recording_manager module-level singleton"
affects: [02-recording-engine, 03-playback-timeline, 04-clip-export, 05-retention-cleanup]

tech-stack:
  added: []
  patterns: ["FFmpeg segmented recording with MPEG-TS", "Exponential backoff retry [0,5,10,30,60]", "Watchdog 2x segment_duration", "SSE status broadcasting"]

key-files:
  created: ["backend/app/services/recording.py"]
  modified: []

key-decisions:
  - "Used asyncio.create_subprocess_exec for FFmpeg — non-blocking subprocess management"
  - "SSE status events broadcast directly via sse_queues from notifications module — no intermediate event bus"
  - "Segment scanner uses 30s mtime cutoff to avoid reading in-progress files"
  - "Mirrored capture.py sun event logic for recording window with recording-specific fields"

patterns-established:
  - "RecordingProcess per-profile pattern: one FFmpeg subprocess per profile with independent lifecycle"
  - "RecordingManager.restore_all pattern: query all recording_enabled profiles on startup"
  - "Relative path storage: segments stored as recordings/{profile_id}/{filename} relative to DATA_DIR"

requirements-completed: [REC-01, REC-03]

duration: 2min
completed: 2026-03-30
---

# Phase 02 Plan 01: Recording Engine Core Summary

**RecordingManager singleton with FFmpeg segmented MPEG-TS recording, exponential backoff retry, watchdog detection, and filesystem segment scanner**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-30T19:18:33Z
- **Completed:** 2026-03-30T19:20:30Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- RecordingManager singleton managing per-profile FFmpeg recording subprocesses
- FFmpeg segmented recording with `-f segment -segment_format mpegts -c copy` and RTSP TCP transport with 5-second timeouts
- Exponential backoff retry on FFmpeg exit (0/5/10/30/60s schedule) with watchdog kill-restart at 2× segment_duration
- RTSP URL resolution for both go2rtc (via RTSP port 8554) and direct RTSP sources
- Recording window evaluation supporting always/scheduled/sun/manual modes with day-of-week filtering
- Filesystem segment scanner registering new .ts files in recording_segments table with ffprobe duration

## Task Commits

Each task was committed atomically:

1. **Task 1: Create RecordingProcess and RecordingManager with FFmpeg lifecycle** - `395ab80` (feat)
2. **Task 2: Add segment scanner and ffprobe duration helper** - `da5f094` (feat)

## Files Created/Modified
- `backend/app/services/recording.py` — Core recording engine with RecordingManager, RecordingProcess, segment scanner, URL resolver, and recording window evaluator

## Decisions Made
- Used asyncio.create_subprocess_exec for non-blocking FFmpeg management
- SSE status events broadcast directly via sse_queues — no intermediate event bus needed
- 30-second mtime cutoff in scanner avoids reading in-progress segment files
- Mirrored capture.py sun event logic with recording-specific profile fields

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness
- RecordingManager ready to be wired into application lifecycle (Plan 02)
- scan_segments ready to be registered as APScheduler job (Plan 02)
- SSE status events ready for frontend consumption

## Self-Check: PASSED

---
*Phase: 02-recording-engine*
*Completed: 2026-03-30*
