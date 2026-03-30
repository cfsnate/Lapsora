# Phase 4: Playback Infrastructure — Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Full-stack playback: dynamic HLS playlist generation, segment serving, and a unified live+recording player with a zoomable timeline scrubber, gap visualization, and playback speed controls. This phase merges the original Phase 4 (HLS backend) and Phase 5 (Timeline UI & Live View) into a single deliverable. Users can watch live and scrub back through recorded history on the same page.

**In scope:**
- Dynamic `.m3u8` VOD playlist generation from SQLite segment metadata
- Segment serving API with path validation and Range request support
- Recording availability API for timeline gap visualization
- Reusable HLS.js player Svelte component with slot-based architecture
- Unified stream page: same `<video>` element for live and recorded playback
- Zoomable timeline bar with date/time picker navigation
- Gap rendering on the timeline
- Playback speed controls (0.5x–8x)
- `#EXT-X-PROGRAM-DATE-TIME` tags for wall-clock alignment

**Out of scope (later phases):**
- Clip export (Phase 5, was Phase 6)
- Recording notifications (Phase 6, was Phase 7)
- Keyboard shortcuts for playback (v2)
- Multi-camera synchronized playback (out of scope)
</domain>

<decisions>
## Decisions Made

### Playlist Windowing: Frontend-driven 1-hour range
- Frontend requests playlist for a 1-hour window around the user's selected time
- When the user seeks beyond the window, frontend requests a new playlist centered on the seek target
- 1-hour windows are fast to load, ideal for the expected heavy scrubbing usage pattern
- No fixed chunk alignment — windows are centered on the user's position

### Segment Serving: Hybrid approach
- Playlist references segment IDs (not raw file paths)
- API route `GET /api/playback/segment/{segment_id}` validates the segment exists in the DB, resolves the file path, and serves via `FileResponse` (which handles Range requests)
- Path traversal impossible — only segments with matching DB records are served
- Consistent with existing `FileResponse` patterns for timelapse/capture downloads

### Player Component: Reusable shell with slot architecture
- Svelte component wrapping HLS.js: video element + controls slot + event emitter for seek/play/pause
- Designed for Phase 5 clip export to reuse the same player
- Same `<video>` element for live and recorded — source switches seamlessly

### Live ↔ Recording Transition: Same video element
- When user scrubs back in time, HLS.js switches from live stream source to recording playlist source
- Scrubbing back to "now" switches back to live
- No separate players or tab switching — fluid in-place transition

### Gap Data: Availability API
- Dedicated endpoint `GET /api/playback/{profile_id}/availability?date=YYYY-MM-DD` returns array of `{start, end}` ranges where recordings exist
- Frontend renders the inverse (non-covered ranges) as gaps on the timeline
- Separate from playlist generation — used for full-day/multi-day overview

### Timeline Navigation: Date/time picker + zoomable timeline
- A date/time picker for jumping to specific dates
- A zoomable horizontal timeline bar (scroll/pinch to zoom from 1-hour to multi-day view)
- Timeline shows recording availability as filled regions, gaps as empty/hatched

### Segment Format: Keep MPEG-TS
- Segments are already `.ts` files on disk from the recording engine
- HLS.js plays MPEG-TS natively — zero conversion overhead
- No need for fMP4 conversion at this stage

### Playback Speed: 0.5x–8x
- Speed control via HLS.js `playbackRate` API
- Preset buttons: 0.5x, 1x, 2x, 4x, 8x
</decisions>

<existing_patterns>
## Relevant Existing Patterns

### Static file serving
- Captures: `app.mount("/static/captures", StaticFiles(...))`
- Timelapses: `app.mount("/static/timelapses", StaticFiles(...))`
- Downloads: `FileResponse` with media_type for timelapse/capture downloads

### Frontend component patterns
- Stream cards with live view on `/streams/{id}` page
- SSE events for real-time updates (recording status badges)
- API client facade in `frontend/src/lib/api.ts`
- TypeScript interfaces in `frontend/src/lib/types.ts`

### Data available from prior phases
- `RecordingSegment` model with `profile_id`, `start_time`, `duration_seconds`, `file_path`, `file_size_bytes`, `protected`
- Recording files at `DATA_DIR/recordings/{profile_id}/YYYY-MM-DD/HH/` as `.ts` segments
- `recording_segments` table indexed by `profile_id` and `start_time`
- Profile recording status via SSE events

### Stream source resolution
- `StreamSourceResolver` class resolves go2rtc vs direct RTSP URLs
- Live view already works on the stream detail page
</existing_patterns>

<tech_context>
## Technical Context

### HLS.js
- De facto HLS player for browsers (hls.js npm package)
- Handles `.m3u8` parsing, segment fetching, buffer management, seeking
- `Hls.Events.MANIFEST_PARSED` → ready to play
- `Hls.Events.ERROR` → handle network/media errors
- `playbackRate` property for speed control
- VOD playlist with `#EXT-X-ENDLIST` for recorded playback
- `#EXT-X-PROGRAM-DATE-TIME` for wall-clock alignment
- `#EXT-X-DISCONTINUITY` for gap boundaries within a playlist

### Dynamic m3u8 Generation
```
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:300
#EXT-X-PLAYLIST-TYPE:VOD
#EXT-X-PROGRAM-DATE-TIME:2026-03-30T10:00:00Z
#EXTINF:300.0,
/api/playback/segment/42
#EXT-X-PROGRAM-DATE-TIME:2026-03-30T10:05:00Z
#EXTINF:300.0,
/api/playback/segment/43
#EXT-X-ENDLIST
```

### FastAPI FileResponse
- Supports Range requests (HTTP 206 Partial Content) automatically
- Sets Content-Type and Content-Length headers
- Used for timelapse and capture downloads already

### Timeline Zoom Library Options
- Custom canvas/SVG-based timeline (most control, common in NVR UIs)
- d3-zoom for zoomable SVG timelines
- vanilla JS with transform scaling
</tech_context>

<boundaries>
## Phase Boundaries

### What MUST be true when this phase is done
1. User can play back recorded footage for any time range with seamless cross-segment transitions via HLS
2. Footage streams via HLS without requiring full file downloads
3. Playback works in Chrome, Firefox, and Safari without plugins
4. User can navigate to any point in recorded history via a visual timeline scrubber with date/time selection
5. Gaps where recording is missing are visually indicated on the timeline
6. Live stream and recording timeline appear on the same page for each profile
7. User can adjust playback speed from 0.5x to 8x

### Requirements covered
- PLAY-01: Timeline scrubber with date/time selection
- PLAY-02: Gap visualization
- PLAY-03: Seamless HLS playback
- PLAY-04: Live stream + recording on same page
- PLAY-05: Playback speed 0.5x–8x
</boundaries>
