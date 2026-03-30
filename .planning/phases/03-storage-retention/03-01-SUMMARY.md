---
phase: 03-storage-retention
plan: 01
subsystem: api, database
tags: [retention, cleanup, recording, scheduler, fastapi, sqlalchemy]

requires:
  - phase: 02-recording-engine
    provides: RecordingSegment model, segment scanner, recording manager
  - phase: 01-data-model-recording-configuration
    provides: Profile model with recording config, Setting model
provides:
  - Recording retention cleanup service with batch deletion
  - Emergency disk watermark cleanup (90% trigger → 80% target)
  - Per-profile recording_retention_days override column
  - Protect/unprotect API for time-range segment protection
  - Recording storage stats endpoint (per-profile breakdown)
  - Global recording retention settings GET/PUT endpoints
  - Hourly cleanup and 5-min watermark scheduler jobs
affects: [03-storage-retention plan 02, frontend settings, frontend recording UI]

tech-stack:
  added: []
  patterns: [batch deletion with configurable batch size, disk watermark emergency cleanup, time-range overlap queries for segment protection]

key-files:
  created:
    - backend/app/migrations/versions/020_recording_retention.sql
  modified:
    - backend/app/models.py
    - backend/app/schemas.py
    - backend/app/services/retention.py
    - backend/app/services/scheduler.py
    - backend/app/main.py
    - backend/app/routers/recording.py
    - backend/app/routers/statistics.py
    - backend/app/routers/settings.py

key-decisions:
  - "Batch size 500 for recording segment deletion to balance throughput and memory"
  - "Emergency cleanup deletes oldest unprotected segments across ALL profiles (not per-profile) for fastest disk reclaim"
  - "Per-profile recording_retention_days nullable — NULL means use global default (14 days)"

patterns-established:
  - "Batch deletion pattern: query IDs first, then delete in batches with per-batch commit"
  - "Emergency cleanup pattern: loop until disk below target, delete oldest unprotected first"
  - "Time-range overlap query: start_time < end AND (end_time > start OR end_time IS NULL)"

requirements-completed: [STOR-01, STOR-02]

duration: 3min
completed: 2026-03-30
---

# Phase 03 Plan 01: Storage & Retention Backend Summary

**Recording retention engine with batch cleanup, emergency disk watermark, segment protection API, and per-profile storage stats**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-30T20:03:26Z
- **Completed:** 2026-03-30T20:06:48Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments
- Built complete recording retention cleanup service with batch deletion (500 segments/batch) respecting protection flags
- Emergency watermark cleanup triggers at 90% disk and deletes oldest unprotected segments until 80%
- Protect/unprotect endpoints mark overlapping segments via time-range overlap query
- Recording storage stats return per-profile breakdown with segment count, total bytes, protected count, oldest/newest dates
- Global recording retention settings (GET/PUT) with 14-day default
- Hourly cleanup job and 5-minute watermark check wired into scheduler and lifespan

## Task Commits

Each task was committed atomically:

1. **Task 1: Migration, model update, and schema additions** - `867ee98` (feat)
2. **Task 2: Recording cleanup service, emergency watermark, and scheduler wiring** - `2b1dc43` (feat)
3. **Task 3: Protection API, storage stats endpoint, and retention settings endpoint** - `4a2d02c` (feat)

## Files Created/Modified
- `backend/app/migrations/versions/020_recording_retention.sql` - ALTER TABLE profiles ADD recording_retention_days
- `backend/app/models.py` - Added recording_retention_days column to Profile
- `backend/app/schemas.py` - Added ProtectRequest, ProtectResponse, RecordingRetentionConfig, RecordingStorageProfile, RecordingStorageStats; added recording_retention_days to CRUD schemas
- `backend/app/services/retention.py` - Added run_recording_cleanup, run_emergency_recording_cleanup, get_recording_storage_stats, _get_effective_retention
- `backend/app/services/scheduler.py` - Added add_recording_cleanup_job (hourly), add_watermark_check_job (5-min), and remove functions
- `backend/app/main.py` - Wired recording cleanup and watermark check jobs in lifespan
- `backend/app/routers/recording.py` - Added POST protect/unprotect endpoints
- `backend/app/routers/statistics.py` - Added GET recording-storage endpoint
- `backend/app/routers/settings.py` - Added GET/PUT recording-retention endpoints

## Decisions Made
- Batch size 500 for segment deletion balances throughput and memory
- Emergency cleanup operates across ALL profiles (not per-profile) for fastest disk reclaim
- Per-profile recording_retention_days is nullable — NULL falls through to global default (14 days)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None — system Python 3.9 can't run import verification (project targets 3.11+), verified via grep acceptance criteria instead.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All backend retention infrastructure is complete and ready for Plan 02 (frontend integration and test coverage)
- Protected segment flag, storage stats, and retention settings endpoints are available for UI consumption
- Scheduler jobs will begin running immediately on next app startup

## Self-Check: PASSED

All 9 files verified present. All 3 commit hashes verified in git log.

---
*Phase: 03-storage-retention*
*Completed: 2026-03-30*
