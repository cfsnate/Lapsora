# Phase 4: Playback & Timeline - Research

**Researched:** 2026-03-30
**Domain:** HLS video playback, timeline UI, dynamic playlist generation
**Confidence:** HIGH

## Summary

This phase delivers full-stack HLS playback infrastructure: a FastAPI backend that dynamically generates `.m3u8` playlists from SQLite segment metadata and serves `.ts` segments with Range request support, paired with a Svelte 5 frontend featuring an HLS.js player component with live/recording source switching, a zoomable SVG/Canvas timeline with gap visualization, and playback speed controls.

The technical approach is well-proven. HLS.js (v1.6.15) handles MPEG-TS natively — no transcoding or remuxing needed since recordings are already `.ts` segments. Starlette 0.49.3 (shipping with FastAPI 0.128.8) has built-in Range request support in `FileResponse`, so segment serving requires minimal code. The main complexity lies in (1) mapping wall-clock times to HLS seek positions via `#EXT-X-PROGRAM-DATE-TIME` tags, (2) implementing the frontend-driven 1-hour playlist windowing with seamless refetch on seek, and (3) building a zoomable timeline component that renders recording availability and gaps.

**Primary recommendation:** Use HLS.js for Chrome/Firefox with a Safari native-HLS fallback, generate VOD playlists server-side from `RecordingSegment` queries, serve segments by ID via `FileResponse`, and build the timeline as a custom SVG/Canvas Svelte component with wheel-zoom and drag-pan.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Playlist windowing:** Frontend-driven 1-hour range centered on scrub position
- **Segment serving:** Hybrid — API validates segment ID against DB, serves via FileResponse with Range support
- **Player component:** Reusable Svelte shell (video + controls slot + event bus)
- **Live ↔ recording:** Same video element, in-place source switch
- **Gap data:** Availability API per profile per day
- **Timeline:** Date/time picker + zoomable horizontal timeline
- **Segment format:** Keep MPEG-TS (.ts files already on disk)
- **Playback speed:** 0.5x–8x via HLS.js playbackRate

### Claude's Discretion
- Timeline rendering technology (Canvas vs SVG vs hybrid)
- Specific HLS.js configuration parameters
- API response schema shapes
- Component decomposition within the player shell
- Timeline zoom level presets and interaction model

### Deferred Ideas (OUT OF SCOPE)
- Clip export (Phase 5)
- Recording notifications (Phase 6)
- Keyboard shortcuts for playback (v2)
- Multi-camera synchronized playback (out of scope entirely)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLAY-01 | User can navigate recorded history via a timeline scrubber with date/time selection | Timeline component with zoomable bar + date picker; availability API for day overview |
| PLAY-02 | User can see gaps in the timeline where recordings are missing | Availability API returns `{start, end}` ranges; frontend renders inverse as hatched/empty regions |
| PLAY-03 | User can watch recorded footage with seamless cross-segment HLS playback | Dynamic m3u8 generation from RecordingSegment table; HLS.js handles segment transitions via `#EXT-X-DISCONTINUITY` |
| PLAY-04 | User can view live stream and recording timeline on the same page | Same `<video>` element; source swap between go2rtc MSE/WebRTC and HLS.js recorded playback |
| PLAY-05 | User can control playback speed (0.5x–8x) | `videoElement.playbackRate` property; HLS.js transparently adjusts buffer fetching |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| hls.js | 1.6.15 | HLS playback in non-Safari browsers | De facto standard; 15k+ GitHub stars; handles m3u8 parsing, segment fetching, buffer management, error recovery |
| FastAPI FileResponse | (bundled with Starlette 0.49.3) | Segment serving with Range support | Already in use for captures/timelapses; Starlette 0.49+ has automatic HTTP 206 Range support |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none - custom SVG/Canvas) | — | Zoomable timeline scrubber | NVR-style timelines are too domain-specific for generic charting libs; custom Svelte component with `<svg>` or `<canvas>` gives full control |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom timeline | d3-zoom + d3-scale | d3 adds 70KB+ for a single component; custom SVG with `wheel`/`pointer` events is lighter and more Svelte-idiomatic |
| HLS.js for Safari | Native `<video src="playlist.m3u8">` | Safari plays HLS natively without HLS.js; use native for Safari, HLS.js for Chrome/Firefox |
| Canvas timeline | SVG timeline | Canvas better for thousands of elements; SVG simpler for our data density (24h of 5-min segments = ~288 rects). Recommend SVG with Canvas fallback only if perf issues arise with multi-day zoom-out |

**Installation:**
```bash
cd frontend && npm install hls.js@1.6.15
```

No backend dependencies needed — all required packages (FastAPI, SQLAlchemy, Starlette) are already installed.

## Architecture Patterns

### Recommended Project Structure
```
backend/app/
├── routers/
│   └── playback.py          # Playlist generation, segment serving, availability API
├── services/
│   └── playback.py          # Playlist builder logic, segment query helpers

frontend/src/
├── lib/
│   ├── components/
│   │   ├── HlsPlayer.svelte       # Reusable HLS.js + native Safari player shell
│   │   ├── PlaybackControls.svelte # Speed buttons, play/pause, time display
│   │   ├── Timeline.svelte         # Zoomable timeline bar with gap rendering
│   │   └── DatePicker.svelte       # Date/time navigation picker
│   └── stores/
│       └── playback.ts             # Shared playback state (current time, mode, speed)
├── routes/
│   └── streams/
│       └── [id]/
│           └── playback/
│               └── +page.svelte    # Unified live+recording page
```

### Pattern 1: Dynamic m3u8 Playlist Generation
**What:** Server-side VOD playlist built from `RecordingSegment` query results
**When to use:** Every playlist request — no static files, always fresh from DB
**Example:**
```python
# backend/app/services/playback.py
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import RecordingSegment

def generate_playlist(
    db: Session,
    profile_id: int,
    start_time: datetime,
    end_time: datetime,
) -> str:
    segments = (
        db.query(RecordingSegment)
        .filter(
            RecordingSegment.profile_id == profile_id,
            RecordingSegment.start_time < end_time,
            RecordingSegment.start_time >= start_time,
        )
        .order_by(RecordingSegment.start_time.asc())
        .all()
    )

    if not segments:
        return ""

    max_duration = max(
        (s.duration_seconds for s in segments if s.duration_seconds), default=10
    )

    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{int(max_duration) + 1}",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]

    prev_end = None
    for seg in segments:
        if prev_end and seg.start_time > prev_end + timedelta(seconds=1):
            lines.append("#EXT-X-DISCONTINUITY")

        lines.append(
            f"#EXT-X-PROGRAM-DATE-TIME:{seg.start_time.strftime('%Y-%m-%dT%H:%M:%S.000Z')}"
        )
        lines.append(f"#EXTINF:{seg.duration_seconds:.1f},")
        lines.append(f"/api/playback/segment/{seg.id}")
        prev_end = seg.start_time + timedelta(seconds=seg.duration_seconds or 0)

    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines)
```

### Pattern 2: Safari Native HLS Fallback
**What:** Use HLS.js where MSE is available, fall back to native `<video>` on Safari
**When to use:** Always — this is the standard cross-browser pattern
**Example:**
```typescript
// frontend/src/lib/components/HlsPlayer.svelte (initialization logic)
import Hls from 'hls.js';

function attachSource(video: HTMLVideoElement, src: string) {
    if (Hls.isSupported()) {
        const hls = new Hls({
            maxBufferLength: 30,
            maxMaxBufferLength: 60,
        });
        hls.loadSource(src);
        hls.attachMedia(video);
        return hls;
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        // Safari native HLS
        video.src = src;
        return null;
    }
}
```

### Pattern 3: Frontend-Driven Playlist Windowing
**What:** Frontend requests 1-hour playlist windows; re-fetches when user seeks beyond range
**When to use:** For all recording playback — prevents massive playlists for multi-day recordings
**Example:**
```typescript
// When user seeks to a new time outside current window
async function loadWindow(profileId: number, centerTime: Date) {
    const start = new Date(centerTime.getTime() - 30 * 60_000); // 30min before
    const end = new Date(centerTime.getTime() + 30 * 60_000);   // 30min after
    const url = `/api/playback/${profileId}/playlist?start=${start.toISOString()}&end=${end.toISOString()}`;
    hls.loadSource(url);
}
```

### Pattern 4: Live ↔ Recording Source Switch
**What:** Same `<video>` element switches between go2rtc MSE stream and HLS.js recorded playback
**When to use:** On the unified stream page when user scrubs back in time or returns to "now"
**Example:**
```typescript
function switchToRecording(video: HTMLVideoElement, playlistUrl: string) {
    // Detach MSE live source
    if (mseWebSocket) mseWebSocket.close();
    video.src = '';

    // Attach HLS.js
    const hls = new Hls();
    hls.loadSource(playlistUrl);
    hls.attachMedia(video);
}

function switchToLive(video: HTMLVideoElement, wsUrl: string) {
    // Detach HLS.js
    if (hlsInstance) hlsInstance.destroy();

    // Attach go2rtc MSE (same pattern as existing MsePlayer.svelte)
    const mediaSource = new MediaSource();
    video.src = URL.createObjectURL(mediaSource);
    // ... MSE WebSocket setup
}
```

### Anti-Patterns to Avoid
- **Generating playlists for the full recording history:** A profile with weeks of recording would produce a playlist with thousands of entries. Use windowed playlists (1-hour) with frontend re-fetch.
- **Serving segments by file path:** Exposing file system paths in playlist URLs enables path traversal attacks. Always serve by segment ID with DB validation.
- **Creating separate `<video>` elements for live and recording:** Causes visible flicker and layout shift. Reuse the same element with source switching.
- **Using `StreamingResponse` for segment serving:** `FileResponse` already handles Range requests and is more efficient for file I/O. `StreamingResponse` is for dynamically generated content.
- **Hardcoding `#EXT-X-TARGETDURATION`:** Must be >= the longest segment duration in the playlist. Calculate from actual segment data.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HLS parsing/buffering | Custom MSE segment loading | HLS.js | Handles codec detection, buffer management, error recovery, ABR — thousands of edge cases |
| HTTP Range requests | Custom Range header parsing | Starlette `FileResponse` | Built-in since v0.38; handles Content-Range, 206 status, If-Range automatically |
| m3u8 format spec | Custom text templating | String builder with spec constants | Simple enough for VOD; don't add a library, but DO follow HLS spec for tag ordering and required attributes |
| Date/time picker | Custom calendar widget | Native `<input type="datetime-local">` | Browser-native; styled with Tailwind; sufficient for date navigation |

**Key insight:** The HLS spec is simple for VOD playlists (just text concatenation), but the player-side parsing/buffering/error-recovery is extremely complex. Generate playlists server-side (easy), let HLS.js handle playback (hard).

## Common Pitfalls

### Pitfall 1: PROGRAM-DATE-TIME to Seek Position Mapping
**What goes wrong:** Developer tries to seek by wall-clock time but HLS.js seek API uses relative seconds from playlist start, not absolute timestamps.
**Why it happens:** HLS.js `currentTime` is a media offset, not a wall-clock timestamp. `#EXT-X-PROGRAM-DATE-TIME` tags map media time to wall-clock time, but seeking requires converting wall-clock → media offset.
**How to avoid:** Use `hls.playingDate` getter to read current wall-clock position. For seeking, calculate the offset: iterate playlist fragments, find the one whose `programDateTime` matches the target, compute `fragment.start` (relative seconds). Or request a new windowed playlist centered on the target time and start from the beginning.
**Warning signs:** Seeking lands at wrong time; playback starts at playlist beginning instead of target.

### Pitfall 2: DISCONTINUITY Tag Omission Between Non-Contiguous Segments
**What goes wrong:** Playback glitches, audio/video desync, or decoder errors when transitioning between segments that have timestamp gaps.
**Why it happens:** Without `#EXT-X-DISCONTINUITY`, the player assumes PTS continuity between adjacent segments. A gap (e.g., recording was stopped for 2 hours) means PTS jumps, causing decoder confusion.
**How to avoid:** Always insert `#EXT-X-DISCONTINUITY` when the gap between segment end_time and next segment start_time exceeds 1 second. Each segment after a gap should have its own `#EXT-X-PROGRAM-DATE-TIME`.
**Warning signs:** Brief freeze or green frames at segment boundaries; console errors about PTS discontinuity.

### Pitfall 3: Safari ManagedMediaSource vs Standard MSE
**What goes wrong:** `Hls.isSupported()` returns `false` on Safari, but developers try to use HLS.js anyway.
**Why it happens:** Safari uses native HLS support, not MSE. On iOS Safari 17.1+, `ManagedMediaSource` exists but codec checks may fail in some configurations.
**How to avoid:** Always implement the fallback: `if (Hls.isSupported()) { /* use HLS.js */ } else if (video.canPlayType('application/vnd.apple.mpegurl')) { /* set video.src directly */ }`. Safari's native HLS player handles `.m3u8` playlists natively.
**Warning signs:** Black video on Safari; "HLS is not supported" console errors.

### Pitfall 4: FileResponse Content-Type for m3u8
**What goes wrong:** Browser or HLS.js fails to parse playlist because wrong Content-Type header is sent.
**Why it happens:** FastAPI default `FileResponse` uses `text/plain` if no media_type specified.
**How to avoid:** Return playlist with `Response(content=playlist_text, media_type="application/vnd.apple.mpegurl")` for `.m3u8` endpoints. For `.ts` segments, use `media_type="video/mp2t"`.
**Warning signs:** HLS.js emits `MANIFEST_PARSING_ERROR`; browser shows raw text instead of playing video.

### Pitfall 5: Timeline Zoom Performance with Large Date Ranges
**What goes wrong:** Zooming out to a multi-week view renders hundreds of tiny rectangles, causing jank.
**Why it happens:** SVG rendering of many small elements is expensive; each rect triggers a DOM node.
**How to avoid:** At low zoom levels, aggregate availability data into coarser buckets (e.g., hourly summaries instead of per-segment). Only render individual segments when zoomed into a day or closer. Use `requestAnimationFrame` for smooth zoom transitions.
**Warning signs:** Scroll/pinch zoom feels laggy; browser devtools shows long paint times in timeline area.

### Pitfall 6: Playlist Refetch Race Conditions
**What goes wrong:** User scrubs quickly across the timeline; multiple playlist requests fire and responses arrive out of order, loading stale playlists.
**Why it happens:** Each seek triggers a new playlist request; slow network means earlier requests can complete after later ones.
**How to avoid:** Use an `AbortController` for playlist fetches. Cancel the previous request before starting a new one. Debounce rapid scrubbing (e.g., 200ms) before triggering a playlist load.
**Warning signs:** Playback jumps to unexpected times after rapid scrubbing; stale video plays from wrong time window.

## Code Examples

### Dynamic Playlist API Endpoint
```python
# backend/app/routers/playback.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.playback import generate_playlist

router = APIRouter(prefix="/api/playback", tags=["playback"])

@router.get("/{profile_id}/playlist")
def get_playlist(
    profile_id: int,
    start: datetime = Query(...),
    end: datetime = Query(...),
    db: Session = Depends(get_db),
):
    playlist = generate_playlist(db, profile_id, start, end)
    if not playlist:
        raise HTTPException(404, "No recordings found in range")
    return Response(
        content=playlist,
        media_type="application/vnd.apple.mpegurl",
    )
```

### Segment Serving Endpoint
```python
# backend/app/routers/playback.py
import os
from fastapi.responses import FileResponse
from app.config import settings
from app.models import RecordingSegment

@router.get("/segment/{segment_id}")
def get_segment(segment_id: int, db: Session = Depends(get_db)):
    segment = db.get(RecordingSegment, segment_id)
    if not segment:
        raise HTTPException(404, "Segment not found")

    abs_path = os.path.join(settings.DATA_DIR, segment.file_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(404, "Segment file not found on disk")

    return FileResponse(abs_path, media_type="video/mp2t")
```

### Availability API
```python
# backend/app/routers/playback.py
from sqlalchemy import func

@router.get("/{profile_id}/availability")
def get_availability(
    profile_id: int,
    date: str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    day_start = datetime.strptime(date, "%Y-%m-%d")
    day_end = day_start + timedelta(days=1)

    segments = (
        db.query(
            RecordingSegment.start_time,
            RecordingSegment.duration_seconds,
        )
        .filter(
            RecordingSegment.profile_id == profile_id,
            RecordingSegment.start_time >= day_start,
            RecordingSegment.start_time < day_end,
        )
        .order_by(RecordingSegment.start_time.asc())
        .all()
    )

    ranges = []
    for seg in segments:
        end = seg.start_time + timedelta(seconds=seg.duration_seconds or 0)
        if ranges and seg.start_time <= ranges[-1]["end"]:
            ranges[-1]["end"] = max(ranges[-1]["end"], end)
        else:
            ranges.append({
                "start": seg.start_time.isoformat(),
                "end": end.isoformat(),
            })

    return ranges
```

### HLS Player Component (Svelte 5)
```svelte
<!-- frontend/src/lib/components/HlsPlayer.svelte -->
<script lang="ts">
    import Hls from 'hls.js';

    interface Props {
        src: string;
        playbackRate?: number;
        onTimeUpdate?: (time: Date | null) => void;
    }

    let { src, playbackRate = 1, onTimeUpdate }: Props = $props();
    let videoEl = $state<HTMLVideoElement | null>(null);
    let hls = $state<Hls | null>(null);

    $effect(() => {
        if (!videoEl || !src) return;

        if (Hls.isSupported()) {
            const instance = new Hls({
                maxBufferLength: 30,
                maxMaxBufferLength: 60,
            });
            instance.loadSource(src);
            instance.attachMedia(videoEl);
            hls = instance;

            return () => { instance.destroy(); hls = null; };
        } else if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {
            videoEl.src = src;
        }
    });

    $effect(() => {
        if (videoEl) videoEl.playbackRate = playbackRate;
    });
</script>

<!-- svelte-ignore a11y_media_has_caption -->
<video
    bind:this={videoEl}
    playsinline
    class="h-full w-full object-contain"
    ontimeupdate={() => {
        if (hls && onTimeUpdate) {
            onTimeUpdate(hls.playingDate);
        }
    }}
></video>
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flash-based HLS players | HLS.js + MSE API | 2017+ | Flash deprecated; MSE universally available |
| Full-download video files | Segmented HLS streaming | Standard practice | Instant playback start; seek without full download |
| Static pre-generated playlists | Dynamic server-side playlist generation | NVR/DVR standard | No storage overhead for playlists; always fresh from DB |
| iOS required native HLS only | ManagedMediaSource on iOS 17.1+ | 2023 | HLS.js can now work on iOS Safari (with caveats) |
| Starlette manual Range handling | FileResponse built-in Range support | Starlette 0.38+ (2024) | No custom code needed for HTTP 206 |

## Open Questions

1. **Wall-clock seeking precision**
   - What we know: HLS.js `playingDate` getter returns current wall-clock position. `#EXT-X-PROGRAM-DATE-TIME` maps fragments to wall-clock time.
   - What's unclear: No built-in `seekToDate(date)` method in HLS.js. Seeking requires converting wall-clock → media offset manually, or simply requesting a new playlist window centered on the target time and playing from the start.
   - Recommendation: Use the playlist-refetch approach — when user clicks a point on the timeline, request a new 1-hour playlist centered on that time. This avoids complex offset math and naturally handles discontinuities.

2. **Multi-day availability aggregation**
   - What we know: The availability API returns per-day ranges. For a zoomed-out multi-week view, this means many API calls.
   - What's unclear: Performance of querying availability across many days simultaneously.
   - Recommendation: Add an optional `days` parameter to the availability API for batch queries, or implement a summary endpoint that returns daily boolean availability for a date range (lighter weight for zoom-out views).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (backend), vitest (frontend) |
| Config file | No explicit config files — pytest uses defaults, vitest configured via `package.json` script |
| Quick run command | `cd backend && python -m pytest tests/test_playback.py -x` |
| Full suite command | `cd backend && python -m pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAY-01 | Timeline scrubber with date/time selection | manual | Manual browser test — Svelte component interaction | ❌ Wave 0 |
| PLAY-02 | Gaps visible on timeline | unit | `python -m pytest tests/test_playback.py::test_availability_gaps -x` | ❌ Wave 0 |
| PLAY-03 | Seamless HLS playback across segments | unit + integration | `python -m pytest tests/test_playback.py::test_playlist_generation -x` | ❌ Wave 0 |
| PLAY-04 | Live + recording on same page | manual | Manual browser test — source switching | ❌ Wave 0 |
| PLAY-05 | Playback speed 0.5x–8x | manual | Manual browser test — `playbackRate` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_playback.py -x`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_playback.py` — covers PLAY-02, PLAY-03 (playlist generation, availability, segment serving)
- [ ] Test fixtures for RecordingSegment creation in conftest or test file

## Sources

### Primary (HIGH confidence)
- npm registry: hls.js v1.6.15 (verified via `npm view hls.js version`)
- Starlette 0.49.3 / FastAPI 0.128.8 (verified via `pip show`)
- Existing codebase: `RecordingSegment` model, `FileResponse` patterns, `MsePlayer.svelte`, `api.ts` client facade
- HLS spec: `#EXT-X-PROGRAM-DATE-TIME`, `#EXT-X-DISCONTINUITY`, `#EXT-X-PLAYLIST-TYPE:VOD` tag semantics

### Secondary (MEDIUM confidence)
- HLS.js GitHub README and API docs — `Hls.isSupported()`, `playingDate`, `playbackRate` via video element
- HLS.js GitHub issue #5356 — no built-in `seekToDate()`, confirmed by absence in API docs
- Starlette PR #2697 — Range request support merged, shipped in 0.38+

### Tertiary (LOW confidence)
- NVR timeline UI patterns — based on general NVR software observation, no specific verified implementation reference

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — hls.js 1.6.15 verified on npm; Starlette Range support verified via version check
- Architecture: HIGH — follows existing project patterns (FileResponse, router/service split, api.ts client)
- Pitfalls: HIGH — based on HLS spec knowledge and verified HLS.js API limitations
- Timeline UI: MEDIUM — custom component recommended based on domain requirements; no verified Svelte-specific NVR timeline library exists

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (stable domain; HLS.js and FastAPI move slowly)
