# Roadmap: Lapsora — Recording, Playback & Clip Export

## Overview

This milestone adds NVR-style continuous recording, browser-based HLS playback with a timeline scrubber, and clip export to Lapsora's existing timelapse infrastructure. The work follows a strict dependency chain: data models and configuration first, then the recording engine that produces segments, storage management before disk fills, HLS serving infrastructure, the timeline UI on top, clip export using all prior layers, and notifications to tie it together. Each phase delivers one complete, verifiable capability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Data Model & Recording Configuration** - Schema, migrations, and per-profile recording settings API and UI
- [ ] **Phase 2: Recording Engine** - FFmpeg segmented recording with process management, watchdog, and auto-recovery
- [ ] **Phase 3: Storage & Retention** - Rolling retention auto-cleanup and segment protection
- [ ] **Phase 4: Playback Infrastructure** - Dynamic HLS playlist generation and segment serving for browser playback
- [ ] **Phase 5: Timeline UI & Live View** - Timeline scrubber, gap visualization, live+recording combined page, and playback speed
- [ ] **Phase 6: Clip Export** - Time-range clip extraction with format/quality options and independent export queue
- [ ] **Phase 7: Recording Notifications** - Recording event, failure, and storage warning notifications

## Phase Details

### Phase 1: Data Model & Recording Configuration
**Goal**: Users can configure recording settings for each camera profile
**Depends on**: Nothing (first phase)
**Requirements**: REC-02, REC-05
**Success Criteria** (what must be TRUE):
  1. User can enable or disable recording per profile through the settings UI
  2. User can configure segment duration and storage path per profile
  3. User can define recording schedules with time-of-day and day-of-week windows per profile
  4. Recording configuration persists across application restarts
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md — Backend data layer: migration, models, schemas, router, tests
- [x] 01-02-PLAN.md — Frontend types and recording settings UI

**UI hint**: yes

### Phase 2: Recording Engine
**Goal**: Cameras continuously record video to disk with automatic failure recovery
**Depends on**: Phase 1
**Requirements**: REC-01, REC-03, REC-04
**Success Criteria** (what must be TRUE):
  1. Enabled profiles produce playable MPEG-TS segment files on disk via FFmpeg segmented output
  2. Recording automatically resumes after stream disconnect without user intervention
  3. User can see recording status (active / stopped / error) for each profile in the UI
  4. Recording processes survive application restart and resume for enabled profiles
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — Core recording engine service (RecordingManager, FFmpeg lifecycle, segment scanner)
- [ ] 02-02-PLAN.md — Backend integration and recording status API
- [ ] 02-03-PLAN.md — Frontend recording status indicators on stream cards

**UI hint**: yes

### Phase 3: Storage & Retention
**Goal**: Recording storage is automatically managed so the disk never fills uncontrolled
**Depends on**: Phase 2
**Requirements**: STOR-01, STOR-02
**Success Criteria** (what must be TRUE):
  1. Old recording segments are automatically deleted when they exceed the configured rolling retention window
  2. User can protect specific recording segments to exempt them from auto-cleanup
  3. User can see current recording storage usage per profile
**Plans**: TBD

### Phase 4: Playback Infrastructure
**Goal**: Users can watch recorded footage via seamless HLS playback in the browser
**Depends on**: Phase 3
**Requirements**: PLAY-03
**Success Criteria** (what must be TRUE):
  1. User can play back recorded footage for any time range with seamless cross-segment transitions
  2. Footage streams via HLS without requiring full file downloads
  3. Playback works in Chrome, Firefox, and Safari without plugins
**Plans**: TBD
**UI hint**: yes

### Phase 5: Timeline UI & Live View
**Goal**: Users can navigate their full recording history and monitor live streams from one page
**Depends on**: Phase 4
**Requirements**: PLAY-01, PLAY-02, PLAY-04, PLAY-05
**Success Criteria** (what must be TRUE):
  1. User can navigate to any point in recorded history via a visual timeline scrubber with date/time selection
  2. Gaps where recording is missing are visually indicated on the timeline
  3. Live stream and recording timeline appear on the same page for each profile
  4. User can adjust playback speed from 0.5x to 8x
**Plans**: TBD
**UI hint**: yes

### Phase 6: Clip Export
**Goal**: Users can extract specific moments from recordings as downloadable video files
**Depends on**: Phase 5
**Requirements**: EXPRT-01, EXPRT-02, EXPRT-03
**Success Criteria** (what must be TRUE):
  1. User can select start and end times and export that range as a video clip
  2. User can choose export format and quality options before exporting
  3. Clip exports run in a separate queue that does not block timelapse generation
  4. Exported clips are downloadable from the UI
**Plans**: TBD
**UI hint**: yes

### Phase 7: Recording Notifications
**Goal**: Users are informed of recording events and storage issues without monitoring the UI
**Depends on**: Phase 2
**Requirements**: NOTIF-01, NOTIF-02, NOTIF-03
**Success Criteria** (what must be TRUE):
  1. User receives notification when recording starts or stops on any profile
  2. User receives notification when recording fails or a stream disconnects
  3. User receives warning when recording storage exceeds configured thresholds
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Model & Recording Configuration | 0/2 | Not started | - |
| 2. Recording Engine | 0/? | Not started | - |
| 3. Storage & Retention | 0/? | Not started | - |
| 4. Playback Infrastructure | 0/? | Not started | - |
| 5. Timeline UI & Live View | 0/? | Not started | - |
| 6. Clip Export | 0/? | Not started | - |
| 7. Recording Notifications | 0/? | Not started | - |
