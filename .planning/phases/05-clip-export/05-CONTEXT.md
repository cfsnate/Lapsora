# Phase 5: Clip Export — Context

**Gathered:** 2026-03-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Clip export feature: users select a time range on the timeline, configure export options (quality, resolution, format), and submit to an independent export queue. FFmpeg extracts the clip from recorded segments via the concat demuxer. Completed clips are downloadable from a dedicated exports page.

**In scope:**
- Export queue service (independent from timelapse generation queue)
- FFmpeg clip extraction via concat demuxer with stream copy or re-encode
- Quality presets: Original (stream copy), High (CRF 18), Medium (CRF 23), Low (CRF 28)
- Resolution options: Original, 1080p, 720p, 480p (only when quality is not "Original")
- Format: MP4
- Timeline range selection (drag-select start/end markers) on the playback page
- Export dialog with editable time fields for fine-tuning
- Dedicated `/exports` page listing all exports with status, progress, download links
- ClipExport model status tracking (pending → processing → completed/failed)
- Export API endpoints (create, list, download, cancel/delete)

**Out of scope (later phases or v2):**
- Recording notifications including export events (Phase 6)
- Export progress via real-time SSE (EXPRT-04, v2)
- Export complete notifications via Apprise (EXPRT-05, v2)
- WebM/MKV containers
- Batch export
</domain>

<decisions>
## Decisions Made

### Queue Architecture: Separate export queue
- New `ExportQueue` service, same pattern as existing `GenerationQueue` but fully independent
- Own worker, own concurrency limit (1 concurrent export by default)
- Exports and timelapses can run simultaneously without blocking each other
- Queue persists across restarts via `ClipExport` model status in SQLite

### FFmpeg Approach: Stream copy default, re-encode for quality presets
- **Original quality:** FFmpeg concat demuxer + stream copy (`-c copy`). Fast, no quality loss. Clips snap to nearest keyframe at start/end (~1-2s margin). This is the default.
- **High/Medium/Low quality:** FFmpeg concat demuxer + re-encode with H.264 (libx264). Boundary trimming is frame-accurate. Slower, proportional to clip duration.
- Concat list built from `RecordingSegment` rows overlapping the requested time range
- `-ss` offset into first segment, `-to` for total duration

### Quality Presets: Original + 3 presets
| Preset | Codec | CRF | Speed | Notes |
|--------|-------|-----|-------|-------|
| Original | copy | N/A | Fast | Stream copy, keyframe-snapped boundaries |
| High | libx264 | 18 | Slow | Near-lossless, large files |
| Medium | libx264 | 23 | Medium | Good balance |
| Low | libx264 | 28 | Fast | Small files, visible compression |

### Resolution Options: Available when re-encoding
- Original (source resolution) — always available
- 1080p, 720p, 480p — only enabled when quality is not "Original"
- Downscale via FFmpeg `-vf scale=-2:720` (maintains aspect ratio)

### Format: MP4 only
- Universal compatibility, sufficient for all use cases
- Container format for H.264 stream copy and re-encode

### Export Initiation: Timeline selection + dialog
- On the playback page, user drags on the timeline to select a start/end range (visual markers appear)
- Clicking "Export Clip" opens a dialog with:
  - Pre-filled start/end times (editable for fine-tuning)
  - Quality preset selector (Original/High/Medium/Low)
  - Resolution dropdown (shown only when quality != Original)
  - "Export" submit button
- Dialog pre-fills from the timeline selection

### Export Management: Dedicated /exports page
- New route `/exports` listing all exports across all streams
- Shows: status (pending/processing/completed/failed), progress percentage, stream name, time range, quality, file size, download link
- Actions: download completed clips, cancel in-progress, delete completed/failed
- Sorted by creation date (newest first)

### ClipExport Model: Already exists
- Created in Phase 1 migration (019_recording_config.sql)
- Fields: id, profile_id, file_path, file_size, format, start_time, end_time, duration_seconds, status, error_message, created_at, completed_at
- May need extension: quality_preset, resolution, progress fields
</decisions>

<existing_patterns>
## Relevant Existing Patterns

### Generation Queue (timelapse)
- `backend/app/services/generation_queue.py` — async queue with `enqueue_generation()`, worker loop
- `backend/app/services/generation_progress.py` — progress tracking with SSE updates
- `backend/app/services/timelapse.py` — FFmpeg-based video generation with subprocess management
- Queue pattern: enqueue → worker picks up → updates status → emits SSE events

### ClipExport Model
- `backend/app/models.py` — `ClipExport` class already defined
- `backend/app/schemas.py` — `ClipExportRead` schema already defined
- `backend/app/migrations/versions/019_recording_config.sql` — table already created

### File serving
- `FileResponse` for timelapse/capture/segment downloads with Range request support
- Static file mounts for captures, timelapses, recordings

### Playback page (Phase 4)
- `frontend/src/routes/streams/[id]/playback/+page.svelte` — unified player with timeline
- `frontend/src/lib/components/Timeline.svelte` — zoomable timeline with gap visualization
- Timeline already has click-to-seek; needs drag-to-select extension for export range

### Existing timelapse exports page pattern
- `frontend/src/routes/timelapses/+page.svelte` — listing page with download/delete actions
</existing_patterns>

<boundaries>
## Phase Boundaries

### What MUST be true when this phase is done
1. User can select start and end times and export that range as a video clip
2. User can choose export format and quality options before exporting
3. Clip exports run in a separate queue that does not block timelapse generation
4. Exported clips are downloadable from the UI

### Requirements covered
- EXPRT-01: Select start/end times, export as MP4 clip
- EXPRT-02: Choose export format and quality options
- EXPRT-03: Independent export queue
</boundaries>
