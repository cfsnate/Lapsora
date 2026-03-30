---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verifying
stopped_at: Completed 05-04-PLAN.md
last_updated: "2026-03-30T23:07:44.469Z"
last_activity: 2026-03-30
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 14
  completed_plans: 14
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-30)

**Core value:** Users can record, review, and export video from their RTSP cameras without relying on cloud services or third-party NVR software.
**Current focus:** Phase 05 — clip-export

## Current Position

Phase: 6
Plan: Not started
Status: Phase complete — ready for verification
Last activity: 2026-03-30

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| — | — | — | — |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P02 | 2min | 3 tasks | 3 files |
| Phase 01 P01 | 4min | 3 tasks | 5 files |
| Phase 02 P01 | 2min | 2 tasks | 1 files |
| Phase 02 P03 | 1min | 2 tasks | 5 files |
| Phase 02 P02 | 3min | 2 tasks | 4 files |
| Phase 03 P01 | 3min | 3 tasks | 9 files |
| Phase 03 P02 | 3min | 2 tasks | 4 files |
| Phase 04 P02 | 2min | 2 tasks | 5 files |
| Phase 04 P01 | 3min | 2 tasks | 4 files |
| Phase 04 P03 | 2min | 2 tasks | 3 files |
| Phase 05 P01 | 1min | 2 tasks | 5 files |
| Phase 05 P03 | 3min | 2 tasks | 4 files |
| Phase 05 P02 | 3min | 2 tasks | 3 files |
| Phase 05 P04 | 3min | 2 tasks | 4 files |
| Phase 05 P02 | 3min | 2 tasks | 3 files |
| Phase 05 P04 | 3min | 2 tasks | 4 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- MPEG-TS chosen over MP4 for segment format (crash resilience — no moov atom dependency)
- Windowed HLS playlists to avoid browser overload at multi-day scale
- Independent clip export queue separate from timelapse generation queue
- [Phase 01]: recording_storage_path omitted from UI — server-managed per D-11
- [Phase 01]: segment_duration_seconds omitted from profile duplicate — uses server default per D-10
- [Phase 01]: Recording config stored as flat columns on Profile (consistent with capture_mode pattern)
- [Phase 01]: recording_mode enum: always/scheduled/manual/sun (adds 'scheduled' over capture_mode's 3 values)
- [Phase 02]: Used asyncio.create_subprocess_exec for non-blocking FFmpeg subprocess management
- [Phase 02]: SSE status events broadcast directly via sse_queues — no intermediate event bus
- [Phase 02]: Segment scanner uses 30s mtime cutoff to avoid reading in-progress files
- [Phase 02]: Recording dot placed between health dot and stream name; stream state aggregated from profiles via priority: recording > error > starting > stopped
- [Phase 02]: Used asyncio.run_coroutine_threadsafe for thread-safe sync-to-async bridge in profile endpoints
- [Phase 02]: Recording manager shutdown precedes APScheduler shutdown for clean FFmpeg termination
- [Phase 03]: Batch size 500 for recording segment deletion to balance throughput and memory
- [Phase 03]: Emergency cleanup deletes oldest unprotected segments across ALL profiles for fastest disk reclaim
- [Phase 03]: Per-profile recording_retention_days nullable — NULL means use global default (14 days)
- [Phase 03]: Tests mock SessionLocal to inject test db session — avoids Docker dependency for local testing
- [Phase 03]: Recording bytes shown as green segment between captures (blue) and timelapses (purple) in disk bar
- [Phase 04]: getPlaylistUrl/getSegmentUrl return URL strings (not fetch) — HLS.js loads URLs directly
- [Phase 04]: generate_playlist returns empty string for no segments, router converts to 404
- [Phase 04]: Availability ranges merged in-place using isoformat comparison for overlap detection
- [Phase 04]: Single UnifiedPlayer component drives both live and recording — no separate player imports on playback page
- [Phase 04]: Auto-refetch HLS playlist when playback time approaches window boundary (within 5 min)
- [Phase 05]: Export queue fully independent from generation queue — no shared state
- [Phase 05]: CRF quality mapping: high=18, medium=23, low=28 for libx264 re-encoding
- [Phase 05]: Stream copy for original quality, FFmpeg concat demuxer for multi-segment clips
- [Phase 05]: ExportDialog mirrors GenerateDialog pattern for UI consistency
- [Phase 05]: Shift+click two-step selection for timeline range picking (start, end, clear cycle)
- [Phase 05]: Polling interval 5s for active exports — matches UI-SPEC recommendation
- [Phase 05]: Export Clip button positioned after speed controls with ml-auto for right-alignment
- [Phase 05]: Export router uses /api/exports prefix with 202 async enqueue on create
- [Phase 05]: Download endpoint validates completed status and file existence before serving
- [Phase 05]: Cancel endpoint uses both queue-level cancel and DB status update for consistency
- [Phase 05]: Export Clip button positioned after speed controls with ml-auto for right-alignment
- [Phase 05]: Polling interval 5s for active exports — matches UI-SPEC recommendation

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-03-30T22:43:20.824Z
Stopped at: Completed 05-04-PLAN.md
Resume file: None
