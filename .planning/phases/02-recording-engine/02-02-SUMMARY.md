---
phase: 02-recording-engine
plan: 02
subsystem: api
tags: [fastapi, apscheduler, recording, lifecycle, ffmpeg]

requires:
  - phase: 02-recording-engine plan 01
    provides: RecordingManager singleton, scan_segments job target, RecordingProcess FFmpeg wrapper
provides:
  - RecordingManager wired into FastAPI lifespan (startup restore, shutdown cleanup)
  - Segment scanner APScheduler job running every 30 seconds
  - Recording status REST API at /api/recording/status
  - Profile update/delete hooks triggering recording start/stop
affects: [03-playback-ui, 04-clip-export]

tech-stack:
  added: []
  patterns: [asyncio.run_coroutine_threadsafe for sync-to-async bridge in FastAPI sync endpoints]

key-files:
  created: [backend/app/routers/recording.py]
  modified: [backend/app/main.py, backend/app/services/scheduler.py, backend/app/routers/profiles.py]

key-decisions:
  - "Used asyncio.run_coroutine_threadsafe to bridge sync endpoints to async RecordingManager"
  - "Segment scanner job added after restore_jobs and gap check, before generation worker start"
  - "Recording manager shutdown runs before APScheduler shutdown to cleanly terminate FFmpeg processes"

patterns-established:
  - "Lazy import of recording_manager inside route handlers to avoid circular imports"
  - "run_coroutine_threadsafe pattern for sync-to-async calls in profile mutation endpoints"

requirements-completed: [REC-01, REC-04]

duration: 3min
completed: 2026-03-30
---

# Phase 02 Plan 02: Recording Lifecycle Wiring Summary

**RecordingManager wired into FastAPI lifespan with segment scanner scheduling and recording status REST API**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-30T19:22:32Z
- **Completed:** 2026-03-30T19:25:13Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- RecordingManager starts on app boot (restore_all) and shuts down cleanly before scheduler teardown
- Segment scanner APScheduler job runs every 30 seconds to discover new .ts files
- Profile update with recording field changes triggers recording restart or stop via run_coroutine_threadsafe
- Profile deletion stops any active recording for that profile
- Recording status API serves GET /api/recording/status (all profiles) and GET /api/recording/status/{profile_id}

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire RecordingManager into application lifecycle and profile hooks** - `6797f67` (feat)
2. **Task 2: Create recording status API router** - `1943448` (feat)

## Files Created/Modified
- `backend/app/routers/recording.py` - Recording status API with GET /status and GET /status/{profile_id}
- `backend/app/main.py` - Lifespan recordings dir, recording_manager restore/shutdown, segment scanner job, router include
- `backend/app/services/scheduler.py` - add_segment_scanner_job and remove_segment_scanner_job functions
- `backend/app/routers/profiles.py` - Recording manager hooks on profile update and delete

## Decisions Made
- Used `asyncio.run_coroutine_threadsafe` instead of `loop.create_task` for thread-safe async scheduling from sync endpoints
- Recording manager shutdown placed before APScheduler shutdown to ensure FFmpeg processes terminate cleanly before job scheduler stops
- Segment scanner job registered after capture restore_jobs and gap check, before generation worker start

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Used asyncio.run_coroutine_threadsafe instead of loop.create_task**
- **Found during:** Task 1 (profile hooks)
- **Issue:** Plan suggested `loop.create_task()` from sync endpoints, but `create_task` is not thread-safe when called from threadpool workers running sync FastAPI endpoints
- **Fix:** Used `asyncio.run_coroutine_threadsafe(coro, loop)` which is the documented thread-safe way to schedule coroutines from non-event-loop threads
- **Files modified:** backend/app/routers/profiles.py
- **Verification:** Syntax check passes; run_coroutine_threadsafe is the correct asyncio API for cross-thread scheduling
- **Committed in:** 6797f67

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Thread-safety fix — necessary for correctness in sync-to-async bridge. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Recording status API ready for frontend consumption in Phase 03 (playback UI)
- RecordingManager fully integrated — starts on boot, reacts to profile changes, exposes status
- Segment scanner populates RecordingSegment table for timeline/playback queries

---
*Phase: 02-recording-engine*
*Completed: 2026-03-30*
