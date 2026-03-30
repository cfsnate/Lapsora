---
phase: 04-playback-infrastructure
plan: 03
subsystem: ui
tags: [svelte, timeline, hls, mse, playback, video]

requires:
  - phase: 04-playback-infrastructure (Plan 01)
    provides: HLS API endpoints (playlist, segment, availability)
  - phase: 04-playback-infrastructure (Plan 02)
    provides: UnifiedPlayer and PlaybackControls components
provides:
  - Zoomable Timeline component with gap visualization
  - Unified playback page at /streams/[id]/playback/
  - Live + recording mode switching on single page
  - Navigation link from stream detail page
affects: [05-clip-export]

tech-stack:
  added: []
  patterns: [SVG timeline with ResizeObserver, pointer events for zoom/pan/seek]

key-files:
  created:
    - frontend/src/lib/components/Timeline.svelte
    - frontend/src/routes/streams/[id]/playback/+page.svelte
  modified:
    - frontend/src/routes/streams/[id]/+page.svelte

key-decisions:
  - "Single UnifiedPlayer component drives both live and recording — no separate player imports on playback page"
  - "Auto-refetch HLS playlist when playback time approaches window boundary (within 5 min)"

patterns-established:
  - "Timeline zoom/pan via pointer events with pointer capture for smooth dragging"
  - "Derived state for SVG rect computation from availability ranges"

requirements-completed: [PLAY-01, PLAY-02, PLAY-04, PLAY-05]

duration: 2min
completed: 2026-03-30
---

# Phase 4 Plan 3: Timeline & Unified Playback Page Summary

**Zoomable SVG timeline with recording gap visualization and unified live+recording playback page with seamless mode switching**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-30T21:22:09Z
- **Completed:** 2026-03-30T21:24:18Z
- **Tasks:** 2 (+ 1 auto-approved checkpoint)
- **Files modified:** 3

## Accomplishments
- Timeline component with green availability bars, gray gaps, white playhead, hover tooltip, zoom presets (1h/6h/24h/7d), mouse wheel zoom, drag pan, and date picker navigation
- Unified playback page using single UnifiedPlayer component — mode prop switches between live MSE and HLS recording internally
- PlaybackControls integration with speed presets (0.5x-8x), Go Live button, and live badge
- Empty state messaging for cameras with no recordings
- Profile selector dropdown for streams with multiple recording-enabled profiles
- Playback navigation link added to stream detail page header

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Timeline component with zoom and gap visualization** - `9caa396` (feat)
2. **Task 2: Create unified playback page and add navigation link** - `620d53d` (feat)

## Files Created/Modified
- `frontend/src/lib/components/Timeline.svelte` - Zoomable SVG timeline with recording availability bars, gap visualization, playhead, hover tooltip, zoom presets, and date picker
- `frontend/src/routes/streams/[id]/playback/+page.svelte` - Unified playback page with live/recording mode switching via single UnifiedPlayer component
- `frontend/src/routes/streams/[id]/+page.svelte` - Added Playback navigation link in header

## Decisions Made
- Single UnifiedPlayer component on playback page (no separate MsePlayer/HlsPlayer imports) — consistent with Plan 02's unified player architecture
- Auto-refetch HLS playlist when playback approaches window boundary (5-minute threshold) for seamless continuous playback
- Profile change in recording mode preserves current time window and refetches playlist for new profile

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 4 (playback infrastructure) is now complete — all 3 plans executed
- Backend HLS API, unified player components, and user-facing playback page are integrated
- Ready for Phase 5 (clip export) which will add selectable start/end time export from the timeline

## Self-Check: PASSED

- Timeline.svelte: FOUND (218 lines, min 100)
- playback/+page.svelte: FOUND (210 lines, min 80)
- Commit 9caa396: FOUND
- Commit 620d53d: FOUND

---
*Phase: 04-playback-infrastructure*
*Completed: 2026-03-30*
