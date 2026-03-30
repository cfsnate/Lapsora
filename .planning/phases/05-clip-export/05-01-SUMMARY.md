---
phase: 05-clip-export
plan: 01
subsystem: api
tags: [ffmpeg, clip-export, async-queue, libx264, concat-demuxer]

requires:
  - phase: 01-data-model-recording-configuration
    provides: "Recording config columns and clip_exports table"
  - phase: 02-recording-engine
    provides: "Recording segments with file_path, duration, start/end times"
provides:
  - "ClipExport model with quality_preset and resolution columns"
  - "ClipExportCreate schema for request validation"
  - "FFmpeg clip extraction service with quality/resolution options"
  - "Independent async export queue with cancel and restart recovery"
affects: [05-clip-export, 06-recording-notifications]

tech-stack:
  added: []
  patterns: [independent-queue-per-service, ffmpeg-concat-demuxer, crf-quality-presets]

key-files:
  created:
    - backend/app/migrations/versions/021_clip_export_ext.sql
    - backend/app/services/clip_export.py
    - backend/app/services/export_queue.py
  modified:
    - backend/app/models.py
    - backend/app/schemas.py

key-decisions:
  - "Export queue fully independent from generation queue — no shared state"
  - "CRF values: high=18, medium=23, low=28 for libx264 re-encoding"
  - "Stream copy for original quality, libx264 only when re-encoding needed"

patterns-established:
  - "Independent queue module: each async service gets its own queue with cancel/restart"
  - "FFmpeg concat demuxer for multi-segment clip extraction with -ss/-t trimming"

requirements-completed: [EXPRT-01, EXPRT-02, EXPRT-03]

duration: 1min
completed: 2026-03-30
---

# Phase 05 Plan 01: Clip Export Data Layer & Processing Pipeline Summary

**FFmpeg concat demuxer clip extraction with quality presets (CRF 18/23/28) and independent async export queue**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-30T22:31:52Z
- **Completed:** 2026-03-30T22:33:18Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Migration 021 adds quality_preset and resolution columns to clip_exports table
- ClipExport model and ClipExportCreate/ClipExportRead schemas updated with new fields
- clip_export.py service extracts clips via FFmpeg concat demuxer with stream copy or libx264 re-encode
- export_queue.py provides fully independent async queue with enqueue, cancel, worker, and restart recovery

## Task Commits

Each task was committed atomically:

1. **Task 1: Migration + model + schema updates** - `ca24b34` (feat)
2. **Task 2: Clip export service + export queue** - `ef59dd8` (feat)

## Files Created/Modified
- `backend/app/migrations/versions/021_clip_export_ext.sql` - Adds quality_preset and resolution columns
- `backend/app/models.py` - ClipExport model extended with quality_preset and resolution
- `backend/app/schemas.py` - ClipExportCreate added, ClipExportRead updated
- `backend/app/services/clip_export.py` - FFmpeg clip extraction with quality/resolution options
- `backend/app/services/export_queue.py` - Independent async export queue mirroring generation_queue pattern

## Decisions Made
- Export queue is fully independent from generation queue — zero shared state or imports
- CRF quality mapping: high=18, medium=23, low=28 (standard x264 quality tiers)
- Stream copy (`-c copy`) for original quality avoids re-encoding overhead
- Resolution scaling uses `scale=-2:height` to preserve aspect ratio with even-number width
- movflags +faststart on all outputs for web streaming compatibility

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Data layer and processing pipeline ready for API router (plan 02)
- export_queue.start_export_worker() needs to be called from app lifespan
- restore_pending_exports() should be called on startup for crash recovery

## Self-Check: PASSED

All files verified on disk. Both task commits verified in git log.

---
*Phase: 05-clip-export*
*Completed: 2026-03-30*
