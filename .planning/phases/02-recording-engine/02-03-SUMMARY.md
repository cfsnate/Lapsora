---
phase: 02-recording-engine
plan: 03
subsystem: ui
tags: [svelte, sse, recording-status, tailwind, real-time]

requires:
  - phase: 02-recording-engine-01
    provides: "Recording engine backend with FFmpeg subprocess, SSE status broadcasts, /api/recording/status endpoint"
provides:
  - "RecordingStatus TypeScript interface"
  - "Recording status API client methods (getRecordingStatuses, getRecordingStatus)"
  - "Recording status SSE event routing through transient event pipeline"
  - "StreamCard recording dot indicator (red pulsing/amber/gray)"
  - "Streams page recording status fetching and profile-to-stream aggregation"
  - "Real-time recording status updates via SSE listener"
affects: [03-playback-timeline, 04-clip-export]

tech-stack:
  added: []
  patterns:
    - "Profile-to-stream status aggregation (per-profile recording states mapped to stream-level display)"
    - "Transient SSE event pipeline for recording_status (dispatch without persist or toast)"

key-files:
  created: []
  modified:
    - frontend/src/lib/types.ts
    - frontend/src/lib/api.ts
    - frontend/src/routes/+layout.svelte
    - frontend/src/lib/components/StreamCard.svelte
    - frontend/src/routes/streams/+page.svelte

key-decisions:
  - "Recording dot placed between health dot and stream name for visual hierarchy"
  - "Stream recording state aggregated from profiles: recording > error > starting > stopped > null"

patterns-established:
  - "Profile-to-stream mapping: build lookup during profile fetch, reuse for status aggregation"
  - "SSE-driven state updates: listen for CustomEvent, spread-merge into reactive state"

requirements-completed: [REC-04]

duration: 1min
completed: 2026-03-30
---

# Phase 02 Plan 03: Recording Status Indicators Summary

**Colored recording status dots on stream cards — red pulsing for active, amber for error/starting, gray for stopped — driven by real-time SSE events through the transient notification pipeline**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-30T19:22:36Z
- **Completed:** 2026-03-30T19:23:50Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- RecordingStatus TypeScript interface and API client methods for fetching recording statuses
- StreamCard recording dot with Tailwind animate-ping for active recording, amber for error/starting, gray for stopped
- Streams page aggregates per-profile recording states to per-stream display state via profile-to-stream mapping
- Real-time SSE event listener updates recording dots without page refresh

## Task Commits

Each task was committed atomically:

1. **Task 1: Add RecordingStatus type, API methods, and SSE event handling** - `3542d62` (feat)
2. **Task 2: Add recording dot to StreamCard and wire streams page** - `7063ab4` (feat)

## Files Created/Modified
- `frontend/src/lib/types.ts` - Added RecordingStatus interface
- `frontend/src/lib/api.ts` - Added getRecordingStatuses and getRecordingStatus API methods
- `frontend/src/routes/+layout.svelte` - Added recording_status to transient SSE events
- `frontend/src/lib/components/StreamCard.svelte` - Added recordingState prop and colored dot indicator
- `frontend/src/routes/streams/+page.svelte` - Recording status fetching, profile-to-stream mapping, SSE listener

## Decisions Made
- Recording dot placed between health dot and stream name for clear visual hierarchy
- Stream-level recording state uses priority aggregation: recording > error > starting > stopped > null (any profile recording means stream is recording)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Recording status indicators are live and reactive
- Frontend types and API methods ready for playback timeline phase
- SSE pipeline extended for recording events, reusable for future event types

## Self-Check: PASSED

All files exist. All commits verified (`3542d62`, `7063ab4`). All content checks pass.

---
*Phase: 02-recording-engine*
*Completed: 2026-03-30*
