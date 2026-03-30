# Requirements: Lapsora — Recording, Playback & Clip Export

**Defined:** 2026-03-30
**Core Value:** Users can record, review, and export video from their RTSP cameras without relying on cloud services or third-party NVR software.

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Recording

- [x] **REC-01**: User can enable continuous 24/7 recording on a per-profile basis using FFmpeg segmented MPEG-TS output
- [x] **REC-02**: User can configure recording settings per profile (segment duration, storage location, enable/disable)
- [x] **REC-03**: Recording automatically recovers from stream disconnects and resumes when the stream is available
- [x] **REC-04**: User can see recording status indicators (active/stopped/error) for each profile in the UI
- [x] **REC-05**: User can configure recording schedules per profile (time-of-day, day-of-week windows)

### Storage & Retention

- [ ] **STOR-01**: User can configure rolling retention per profile with automatic cleanup of old recording segments
- [ ] **STOR-02**: User can protect specific recording segments to exempt them from auto-cleanup

### Playback

- [ ] **PLAY-01**: User can navigate recorded history via a timeline scrubber with date/time selection
- [ ] **PLAY-02**: User can see gaps in the timeline where recordings are missing
- [ ] **PLAY-03**: User can watch recorded footage with seamless cross-segment HLS playback in the browser
- [ ] **PLAY-04**: User can view live stream and recording timeline on the same page
- [ ] **PLAY-05**: User can control playback speed (0.5x–8x)

### Clip Export

- [ ] **EXPRT-01**: User can select start and end times and export that range as an MP4 clip
- [ ] **EXPRT-02**: User can choose export format and quality options (codec, quality preset)
- [ ] **EXPRT-03**: Clip exports run in an independent queue separate from timelapse generation

### Notifications

- [ ] **NOTIF-01**: User receives notifications when recording starts or stops
- [ ] **NOTIF-02**: User receives notifications when recording fails or stream disconnects
- [ ] **NOTIF-03**: User receives storage warning notifications when recording storage exceeds thresholds

## v2 Requirements

Deferred to future milestone. Tracked but not in current roadmap.

### Storage

- **STOR-03**: Emergency disk watermark cleanup (trigger at 90%, target 80%)
- **STOR-04**: Recording-specific storage dashboard widget with trend charts

### Playback

- **PLAY-06**: Keyboard shortcuts for playback (space for pause, arrow keys for seek)
- **PLAY-07**: Timelapse generation from continuous recording segments

### Export

- **EXPRT-04**: Export progress displayed via real-time SSE notifications
- **EXPRT-05**: Export complete notifications via Apprise

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-camera synchronized playback | Complexity too high for v1; single stream at a time |
| Motion-triggered recording | Requires detection pipeline — different product category |
| Audio recording | Video-only for now; adds codec complexity |
| Real-time object detection/alerts | Frigate's domain, not Lapsora's |
| Cloud storage / remote backup | Self-hosted philosophy |
| Mobile app | Web-first, responsive UI sufficient |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| REC-01 | Phase 2 | Complete |
| REC-02 | Phase 1 | Complete |
| REC-03 | Phase 2 | Complete |
| REC-04 | Phase 2 | Complete |
| REC-05 | Phase 1 | Complete |
| STOR-01 | Phase 3 | Pending |
| STOR-02 | Phase 3 | Pending |
| PLAY-01 | Phase 5 | Pending |
| PLAY-02 | Phase 5 | Pending |
| PLAY-03 | Phase 4 | Pending |
| PLAY-04 | Phase 5 | Pending |
| PLAY-05 | Phase 5 | Pending |
| EXPRT-01 | Phase 6 | Pending |
| EXPRT-02 | Phase 6 | Pending |
| EXPRT-03 | Phase 6 | Pending |
| NOTIF-01 | Phase 7 | Pending |
| NOTIF-02 | Phase 7 | Pending |
| NOTIF-03 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 18 total
- Mapped to phases: 18 ✓
- Unmapped: 0

---
*Requirements defined: 2026-03-30*
*Last updated: 2026-03-30 after roadmap creation*
