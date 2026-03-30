# Lapsora

## What This Is

A self-hosted RTSP timelapse and stream recording web application. Capture frames from RTSP cameras on a schedule, generate timelapse videos, record continuous streams, play back recorded footage with a timeline scrubber, and export video clips — all managed through a modern dark-themed web UI.

## Core Value

Users can record, review, and export video from their RTSP cameras without relying on cloud services or third-party NVR software.

## Requirements

### Validated

- ✓ RTSP and go2rtc stream management with encrypted credentials — existing
- ✓ Stream health monitoring with configurable failure thresholds — existing
- ✓ Scheduled frame capture at configurable intervals — existing
- ✓ HDR / synthetic exposure bracketing with Mertens fusion — existing
- ✓ Sun-based scheduling (sunrise/sunset offsets) — existing
- ✓ Weather data integration (OpenWeatherMap) — existing
- ✓ Timelapse generation (MP4, WebM, GIF) with deflicker, overlays, motion blur — existing
- ✓ GPU acceleration (NVIDIA NVENC, CuPy) — existing
- ✓ Notifications via Apprise + in-app SSE — existing
- ✓ Retention and cleanup schedules — existing
- ✓ Statistics dashboard — existing
- ✓ Profile templates — existing

### Active

- ✓ Per-profile stream recording configuration (enable/disable, schedule, segment settings) — Validated in Phase 1
- ✓ FFmpeg segmented continuous recording into chunked files alongside existing frame capture — Validated in Phase 2
- ✓ Tiered recording retention — rolling auto-cleanup window with ability to protect specific recordings — Validated in Phase 3
- ✓ Timeline scrubber UI for navigating recorded history to any point in time — Validated in Phase 4
- ✓ Combined live view + recording timeline on a single stream page — Validated in Phase 4
- ✓ Clip export with selectable start/end times, format, and quality options — Validated in Phase 5
- [ ] Recording event notifications (started, stopped, failed, export complete, storage warnings)

### Out of Scope

- Multi-stream simultaneous playback — complexity too high for v1, single stream at a time
- Mobile app — web-first, responsive UI sufficient
- Cloud storage / remote backup — self-hosted philosophy
- Audio recording — video-only for now

## Context

Lapsora is an existing, functional timelapse application built with FastAPI (Python) and SvelteKit 5 (TypeScript/Svelte 5 runes). It runs as a single Docker container with SQLite for metadata. The codebase already has solid patterns for stream management, scheduled jobs (APScheduler), FFmpeg integration, file-based media storage, and a generation queue for async video processing. The new recording feature can leverage much of this existing infrastructure — FFmpeg for recording, the generation queue pattern for clip export, the notification system for recording events, and the retention/cleanup system for storage management.

The current branch is `playback-export`, indicating this work is already scoped to a feature branch.

## Constraints

- **Storage:** Continuous recording is storage-intensive; retention configuration and auto-cleanup are essential from day one
- **FFmpeg:** Recording and clip export rely on FFmpeg — must work with the same FFmpeg binary already in the Docker image
- **Single container:** Must fit within the existing single-container deployment model
- **SQLite:** All recording metadata goes through SQLite via SQLAlchemy, same as existing features
- **No auth:** Single-user self-hosted assumption continues — no multi-user access control needed

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| FFmpeg segmented recording | Chunked files enable reliable seeking, resumable recording, and clean clip export boundaries | Implemented — Phase 2 |
| Per-profile recording config | Consistent with existing per-profile capture config; each camera gets independent settings | Implemented — Phase 1 |
| Tiered retention (auto + protect) | Balances storage management with ability to preserve important footage | Implemented — Phase 3 |
| Live view + timeline on same page | Single page for stream monitoring reduces navigation; timeline gives context | Implemented — Phase 4 |
| Clip export mirrors timelapse generation | Reuses format/quality/queue patterns already proven in timelapse workflow | Implemented — Phase 5 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-30 after Phase 5 completion*
