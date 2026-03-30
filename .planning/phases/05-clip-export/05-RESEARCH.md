# Phase 5: Clip Export - Research

**Researched:** 2026-03-30
**Domain:** FFmpeg clip extraction, async queue processing, SvelteKit timeline interaction
**Confidence:** HIGH

## Summary

Phase 5 adds clip export: users select a time range on the existing playback timeline, configure quality/resolution options, and submit to an independent export queue. The backend extracts the clip from recorded MPEG-TS segments using FFmpeg's concat demuxer, either via stream copy (fast, keyframe-snapped) or re-encode (frame-accurate with libx264). Completed clips are downloadable from a dedicated `/exports` page.

The codebase already has strong precedent for every component: `GenerationQueue` for async job processing, `timelapse.py` for FFmpeg subprocess management, `playback.py` for segment querying, `ClipExport` model/schema already created in Phase 1, and the timelapses page for a listing/download UI. The primary work is composing these existing patterns into a new feature.

**Primary recommendation:** Mirror the GenerationQueue pattern for ExportQueue, mirror the playback service's segment query for building concat lists, and extend Timeline.svelte with drag-to-select range markers.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Queue: Separate `ExportQueue` service (same pattern as `GenerationQueue`, independent). Own worker, own concurrency limit (1 concurrent export by default). Persists across restarts via `ClipExport` model status in SQLite.
- FFmpeg: Concat demuxer. "Original" = stream copy (`-c copy`, fast, keyframe-snapped). Other presets = re-encode with libx264 (frame-accurate).
- Quality presets: Original (copy) / High (CRF 18) / Medium (CRF 23) / Low (CRF 28)
- Resolution options: Original / 1080p / 720p / 480p — only when re-encoding (quality != "Original")
- Format: MP4 only
- Export initiation: Timeline drag-select start/end markers + export dialog with editable time fields
- Export management: Dedicated `/exports` page listing all exports with status, progress, download links
- `ClipExport` model already exists from Phase 1 migration (019). May need extension: quality_preset, resolution, progress fields.

### Claude's Discretion
- Internal implementation details of the export service
- SSE event naming and payload structure for export status updates
- File naming convention for exported clips
- Error handling and retry strategy
- How to structure the concat file list from overlapping segments

### Deferred Ideas (OUT OF SCOPE)
- Export progress via real-time SSE (EXPRT-04, v2)
- Export complete notifications via Apprise (EXPRT-05, v2)
- WebM/MKV containers
- Batch export
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXPRT-01 | User can select start and end times and export that range as an MP4 clip | Timeline range selection UI pattern researched; FFmpeg concat demuxer + segment query pattern from `playback.py`; export dialog with editable time fields |
| EXPRT-02 | User can choose export format and quality options (codec, quality preset) | Quality preset CRF values locked; resolution scaling via `-vf scale=-2:N`; format locked to MP4; conditional resolution dropdown when quality != Original |
| EXPRT-03 | Clip exports run in an independent queue separate from timelapse generation | `ExportQueue` mirrors `GenerationQueue` pattern; separate asyncio.Queue + worker task; persists via `ClipExport` model status |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | existing | API endpoints for export CRUD | Project standard |
| SQLAlchemy | existing | ClipExport model ORM | Project standard |
| asyncio.subprocess | stdlib | FFmpeg process management | Project pattern from timelapse.py and recording.py |
| FFmpeg | 8.1 (verified) | Clip extraction via concat demuxer | Project standard, already in Docker image |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Pydantic v2 | existing | Request/response schemas | ClipExportCreate, ClipExportRead schemas |
| SvelteKit 5 | existing | Frontend pages and components | /exports page, ExportDialog, timeline range selection |
| Tailwind CSS v4 | existing | Styling | All frontend components |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| In-memory asyncio.Queue | Celery/Redis | Overkill for single-container deployment, project uses in-memory queues |
| concat demuxer | concat protocol | Protocol can't handle `-ss` offsets into first segment; demuxer is more flexible |
| Re-encoding everything | Stream copy only | Stream copy snaps to keyframes (~1-2s margin); re-encode gives frame-accurate boundaries |

## Architecture Patterns

### Recommended Project Structure
```
backend/app/
├── services/
│   ├── export_queue.py       # ExportQueue (mirrors generation_queue.py)
│   └── clip_export.py        # FFmpeg clip extraction logic
├── routers/
│   └── exports.py            # CRUD endpoints for clip exports
├── migrations/versions/
│   └── 021_clip_export_ext.sql  # Add quality_preset, resolution columns
└── ...existing...

frontend/src/
├── routes/exports/
│   └── +page.svelte           # Exports listing page
├── lib/components/
│   └── ExportDialog.svelte    # Quality/resolution/time export dialog
└── ...existing (Timeline.svelte extended)...
```

### Pattern 1: ExportQueue Service (mirrors GenerationQueue)
**What:** Independent async queue with its own worker task, separate from timelapse generation
**When to use:** For all clip export jobs
**Example:**
```python
# Mirrors backend/app/services/generation_queue.py
_export_queue: asyncio.Queue = asyncio.Queue()
_pending_exports: list[dict] = []
_current_export: dict | None = None

async def enqueue_export(clip_export_id: int, **kwargs) -> dict:
    """Enqueue a clip export job. Returns dict with position."""
    job = {"clip_export_id": clip_export_id, **kwargs}
    with _pending_lock:
        _pending_exports.append(job)
        position = len(_pending_exports)
    await _export_queue.put(job)
    return {"clip_export_id": clip_export_id, "position": position}

async def _export_worker() -> None:
    """Process export jobs one at a time."""
    while True:
        job = await _export_queue.get()
        # ... process with clip_export service ...
```

### Pattern 2: Concat Demuxer Clip Extraction
**What:** Build a concat file list from recording segments, then run FFmpeg to extract the time range
**When to use:** For every clip export
**Example:**
```python
# Query overlapping segments (extends playback.py pattern)
segments = (
    db.query(RecordingSegment)
    .filter(
        RecordingSegment.profile_id == profile_id,
        RecordingSegment.start_time < export_end_time,
        # segment end (start + duration) > export_start_time
    )
    .order_by(RecordingSegment.start_time.asc())
    .all()
)

# Write concat file list
for seg in segments:
    f.write(f"file '{abs_path}'\n")

# Stream copy (Original quality)
cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
       "-ss", str(offset_into_first), "-to", str(total_duration),
       "-c", "copy", output_path]

# Re-encode (High/Medium/Low quality)
cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
       "-ss", str(offset_into_first), "-to", str(total_duration),
       "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
       "-pix_fmt", "yuv420p", output_path]
```

### Pattern 3: Restart Recovery via DB Status
**What:** On app restart, scan `ClipExport` rows with status='pending' or 'processing' and re-enqueue them
**When to use:** In the lifespan handler, after starting the export worker
**Example:**
```python
# In main.py lifespan, after start_export_worker()
from app.services.export_queue import restore_pending_exports
await restore_pending_exports()
```

### Pattern 4: Timeline Range Selection (Svelte 5)
**What:** Extend Timeline.svelte with drag-to-select that sets start/end markers
**When to use:** On the playback page for initiating export
**Example:**
```svelte
<!-- Additional state in Timeline.svelte -->
let selectionStart = $state<Date | null>(null);
let selectionEnd = $state<Date | null>(null);
let isSelecting = $state(false);

<!-- Visual markers for selection range -->
{#if selectionStart && selectionEnd}
  <div class="absolute top-0 h-full bg-blue-500/30"
    style="left: {timeToX(selectionStart)}px; width: {timeToX(selectionEnd) - timeToX(selectionStart)}px;">
  </div>
{/if}
```

### Anti-Patterns to Avoid
- **Reading entire segments into memory:** FFmpeg handles all I/O; the backend only writes a concat file list and runs FFmpeg as a subprocess.
- **Sharing the generation queue:** Exports MUST use their own queue — timelapse generation and clip export run independently per CONTEXT.md.
- **Blocking the event loop:** FFmpeg runs via `asyncio.create_subprocess_exec` (non-blocking), same as timelapse.py.
- **Ignoring keyframe alignment for stream copy:** Document in the UI that "Original" quality snaps to nearest keyframes (~1-2s margin at boundaries).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Video concatenation | Custom frame-by-frame stitching | FFmpeg concat demuxer | Handles format differences, timestamps, codec alignment |
| Video re-encoding | Custom transcoding pipeline | FFmpeg libx264 with CRF | Industry standard, handles all edge cases |
| Async job processing | Custom threading/multiprocessing | asyncio.Queue + worker (existing pattern) | Proven in GenerationQueue, fits single-container model |
| File downloads | Custom streaming implementation | FastAPI FileResponse | Already used for timelapse/segment downloads |
| Duration probing | Custom video parsing | `ffprobe -print_format json -show_format` | Existing pattern in timelapse.py |

**Key insight:** The entire backend clip extraction is an FFmpeg command construction problem. The real complexity is in correctly computing the `-ss` offset and `-to` duration from segment timestamps, and building the concat file list from overlapping segments.

## Common Pitfalls

### Pitfall 1: Incorrect Segment Overlap Query
**What goes wrong:** Missing segments at the boundaries — the first or last segment is excluded because the query doesn't account for segments that START before the export range but EXTEND into it.
**Why it happens:** The playback service queries `start_time >= range_start`, which is correct for HLS playlists (full segments only), but clip export needs segments that overlap the range.
**How to avoid:** Query `start_time < export_end AND (start_time + duration) > export_start` to catch segments that overlap at either boundary.
**Warning signs:** Clips start with black frames or are shorter than expected.

### Pitfall 2: Stream Copy Keyframe Snapping
**What goes wrong:** User expects frame-exact start/end times but "Original" quality gives ~1-2 second margins.
**Why it happens:** `-c copy` can only cut at keyframes (I-frames). MPEG-TS segments typically have keyframes at segment boundaries (~10s intervals from `segment_duration_seconds`).
**How to avoid:** Document this behavior in the export dialog UI. The `-ss` flag before `-i` seeks to the nearest keyframe; after `-i` it's slower but can cut between keyframes (though copy still outputs from the previous keyframe).
**Warning signs:** Users report incorrect start/end times on exported clips.

### Pitfall 3: Concurrent FFmpeg Process Leak
**What goes wrong:** If the export worker crashes or the app shuts down while FFmpeg is running, orphaned FFmpeg processes consume resources.
**Why it happens:** `asyncio.create_subprocess_exec` creates a child process that survives if not explicitly killed.
**How to avoid:** Track the active FFmpeg process (same pattern as `set_active_ffmpeg_proc` in generation_queue.py). Kill it on cancellation or shutdown. Set a timeout on `proc.communicate()`.
**Warning signs:** Multiple FFmpeg processes visible in `ps aux`.

### Pitfall 4: Concat Demuxer with Absolute Paths
**What goes wrong:** FFmpeg concat demuxer fails with "No such file or directory" despite correct paths.
**Why it happens:** The concat demuxer requires `-safe 0` flag when using absolute paths in the file list.
**How to avoid:** Always pass `-safe 0` (already used in timelapse.py). Write absolute paths in the concat file.
**Warning signs:** FFmpeg exits with error immediately.

### Pitfall 5: Missing `-movflags +faststart` for MP4
**What goes wrong:** Large exported MP4 files can't be played until fully downloaded because the moov atom is at the end.
**Why it happens:** Default FFmpeg MP4 muxer writes moov atom at the end of the file.
**How to avoid:** Add `-movflags +faststart` to FFmpeg command. This moves the moov atom to the beginning, enabling progressive playback.
**Warning signs:** Users can't play the clip in-browser until download completes.

### Pitfall 6: ClipExport Status Not Updated on Failure
**What goes wrong:** Failed exports stay in "processing" status forever, blocking the user from understanding what happened.
**Why it happens:** Exception occurs but status isn't updated in the `except` block.
**How to avoid:** Always wrap export logic in try/except/finally. Set status='failed' and error_message in except. Use a finally block for cleanup (temp files).
**Warning signs:** Exports stuck in "processing" in the UI.

## Code Examples

### Segment Overlap Query for Clip Export
```python
from datetime import timedelta
from sqlalchemy import and_

def get_overlapping_segments(db, profile_id, start_time, end_time):
    """Get segments that overlap the requested time range."""
    return (
        db.query(RecordingSegment)
        .filter(
            and_(
                RecordingSegment.profile_id == profile_id,
                RecordingSegment.start_time < end_time,
            )
        )
        .filter(
            (RecordingSegment.start_time + timedelta(seconds=RecordingSegment.duration_seconds)) > start_time
        )
        .order_by(RecordingSegment.start_time.asc())
        .all()
    )
```

Note: SQLAlchemy with SQLite doesn't support datetime arithmetic directly in filters. The practical approach is to query segments in a broader range (`start_time < end_time`) and filter in Python:
```python
segments = (
    db.query(RecordingSegment)
    .filter(
        RecordingSegment.profile_id == profile_id,
        RecordingSegment.start_time < end_time,
    )
    .order_by(RecordingSegment.start_time.asc())
    .all()
)
overlapping = [
    s for s in segments
    if s.start_time + timedelta(seconds=s.duration_seconds or 0) > start_time
]
```

### FFmpeg Concat File + Stream Copy
```python
import tempfile, os

def build_concat_file(segments, data_dir):
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="lapsora_export_")
    with os.fdopen(fd, "w") as f:
        for seg in segments:
            abs_path = os.path.join(data_dir, seg.file_path)
            f.write(f"file '{abs_path}'\n")
    return path

def build_export_cmd(concat_file, offset_seconds, duration_seconds,
                     quality_preset, resolution, output_path):
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    cmd += ["-f", "concat", "-safe", "0", "-i", concat_file]
    cmd += ["-ss", str(offset_seconds), "-t", str(duration_seconds)]

    if quality_preset == "original":
        cmd += ["-c", "copy"]
    else:
        crf_map = {"high": 18, "medium": 23, "low": 28}
        crf = crf_map.get(quality_preset, 23)
        cmd += ["-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
                "-pix_fmt", "yuv420p"]

        if resolution and resolution != "original":
            height_map = {"1080p": 1080, "720p": 720, "480p": 480}
            h = height_map.get(resolution, None)
            if h:
                cmd += ["-vf", f"scale=-2:{h}"]

    cmd += ["-movflags", "+faststart"]
    cmd.append(output_path)
    return cmd
```

### ExportQueue Worker Pattern
```python
async def _export_worker():
    global _current_export
    while True:
        job = await _export_queue.get()
        clip_export_id = job["clip_export_id"]
        _current_export = job
        try:
            await process_clip_export(clip_export_id)
        except Exception:
            logger.exception("Export %d failed", clip_export_id)
        finally:
            _current_export = None
            _export_queue.task_done()
```

### API Router Pattern (mirrors timelapses.py)
```python
router = APIRouter(prefix="/api/exports", tags=["exports"])

@router.post("/", status_code=202)
async def create_export(body: ClipExportCreate, db: Session = Depends(get_db)):
    clip_export = ClipExport(
        profile_id=body.profile_id,
        start_time=body.start_time,
        end_time=body.end_time,
        quality_preset=body.quality_preset,
        resolution=body.resolution,
        status="pending",
    )
    db.add(clip_export)
    db.commit()
    db.refresh(clip_export)
    result = await enqueue_export(clip_export.id)
    return {"status": "queued", "id": clip_export.id, **result}

@router.get("/", response_model=list[ClipExportRead])
def list_exports(db: Session = Depends(get_db)):
    return db.query(ClipExport).order_by(ClipExport.created_at.desc()).all()

@router.get("/{export_id}/download")
def download_export(export_id: int, db: Session = Depends(get_db)):
    export = db.get(ClipExport, export_id)
    if not export or export.status != "completed" or not export.file_path:
        raise HTTPException(404)
    return FileResponse(export.file_path, media_type="video/mp4",
                        filename=os.path.basename(export.file_path))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FFmpeg `-i input -ss time` (slow seek) | `-ss time -i input` (fast seek) | FFmpeg 2.1+ | Fast seek to nearest keyframe before decoding |
| concat protocol (`concat:file1\|file2`) | concat demuxer (`-f concat`) | FFmpeg 1.1+ | Demuxer handles timestamps and discontinuities properly |
| Manual moov atom placement | `-movflags +faststart` | FFmpeg 0.8+ | Enables progressive playback for MP4 |

**Deprecated/outdated:**
- `-strict experimental` for AAC: No longer needed in modern FFmpeg
- `-vcodec` / `-acodec` flags: Use `-c:v` / `-c:a` instead (modern syntax)

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | none — invoked directly |
| Quick run command | `cd backend && python -m pytest tests/test_exports.py -x` |
| Full suite command | `cd backend && python -m pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXPRT-01 | Create export with start/end times, verify DB record | unit | `python -m pytest tests/test_exports.py::test_create_export -x` | ❌ Wave 0 |
| EXPRT-01 | Segment overlap query returns correct segments | unit | `python -m pytest tests/test_exports.py::test_segment_overlap_query -x` | ❌ Wave 0 |
| EXPRT-02 | Export with different quality presets produces different FFmpeg commands | unit | `python -m pytest tests/test_exports.py::test_quality_presets -x` | ❌ Wave 0 |
| EXPRT-02 | Resolution option only applies when quality != Original | unit | `python -m pytest tests/test_exports.py::test_resolution_conditional -x` | ❌ Wave 0 |
| EXPRT-03 | Export queue is independent from generation queue | unit | `python -m pytest tests/test_exports.py::test_independent_queue -x` | ❌ Wave 0 |
| EXPRT-03 | Pending exports restored on app restart | unit | `python -m pytest tests/test_exports.py::test_restore_pending -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_exports.py -x`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_exports.py` — covers EXPRT-01, EXPRT-02, EXPRT-03
- [ ] No framework install needed — pytest already in use

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| FFmpeg | Clip extraction | ✓ | 8.1 | — |
| ffprobe | Duration probing | ✓ | 8.1 | — |
| libx264 | Re-encoding (High/Medium/Low) | ✓ | Bundled | — |
| concat demuxer | Segment concatenation | ✓ | Built-in | — |
| Python 3 | Backend | ✓ | 3.9.6 | — |
| Node.js | Frontend build | ✓ | 22.18.0 | — |

**Missing dependencies with no fallback:** None
**Missing dependencies with fallback:** None

## Database Migration Required

The `clip_exports` table exists (migration 019) but lacks columns for the quality/resolution options specified in CONTEXT.md. A new migration (021) is needed:

```sql
-- Extend clip_exports with quality and resolution options
ALTER TABLE clip_exports ADD COLUMN quality_preset TEXT NOT NULL DEFAULT 'original';
ALTER TABLE clip_exports ADD COLUMN resolution TEXT NOT NULL DEFAULT 'original';
```

The `progress` field mentioned in CONTEXT.md is deferred since EXPRT-04 (real-time progress SSE) is v2. Status tracking (pending/processing/completed/failed) via the existing `status` column is sufficient for v1.

## Open Questions

1. **Export file naming convention**
   - What we know: Timelapse files use `{period_type}_{timestamp}.{ext}` pattern
   - What's unclear: Best naming for exports
   - Recommendation: `clip_{profile_id}_{start_iso}_{end_iso}_{timestamp}.mp4` — includes enough context to identify the clip

2. **Export storage location**
   - What we know: Timelapses go to `data/timelapses/{profile_id}/`, recordings go to `data/recordings/{profile_id}/`
   - What's unclear: Where to store exports
   - Recommendation: `data/exports/{profile_id}/` — consistent with existing pattern, separate from recordings/timelapses

3. **Offset calculation for multi-segment concat**
   - What we know: The concat demuxer treats the file list as one continuous stream. `-ss` is relative to the start of the concatenated stream.
   - What's unclear: Edge case with gaps between segments
   - Recommendation: Calculate `-ss` as the time difference between export start and first segment's start. Calculate `-t` as `export_end - export_start`. FFmpeg handles gaps within segments. If segments have gaps, the output will include the gap (silence/black) — this matches user expectation since they see gaps on the timeline.

## Sources

### Primary (HIGH confidence)
- Codebase: `backend/app/services/generation_queue.py` — ExportQueue pattern source
- Codebase: `backend/app/services/timelapse.py` — FFmpeg subprocess management pattern
- Codebase: `backend/app/services/playback.py` — Segment query pattern
- Codebase: `backend/app/models.py` — ClipExport model definition
- Codebase: `backend/app/migrations/versions/019_recording_config.sql` — clip_exports table schema
- Codebase: `frontend/src/lib/components/Timeline.svelte` — Timeline interaction pattern
- Codebase: `frontend/src/routes/timelapses/+page.svelte` — Listing page pattern
- Environment: FFmpeg 8.1 verified with libx264, concat demuxer, MP4 muxer

### Secondary (MEDIUM confidence)
- FFmpeg concat demuxer documentation — standard usage patterns for segment concatenation
- FFmpeg seeking documentation — `-ss` before vs after `-i` behavior

### Tertiary (LOW confidence)
- None — all findings verified against codebase and environment

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — using only existing project dependencies
- Architecture: HIGH — mirrors proven GenerationQueue + timelapse.py patterns exactly
- Pitfalls: HIGH — derived from actual codebase patterns and FFmpeg behavior verified in environment

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (stable — all components are existing project patterns)
