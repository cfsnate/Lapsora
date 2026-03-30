---
phase: 4
slug: playback-infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-30
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend), manual browser testing (frontend) |
| **Config file** | none — pytest uses defaults |
| **Quick run command** | `cd backend && python -m pytest tests/test_playback.py -x` |
| **Full suite command** | `cd backend && python -m pytest tests/ -x` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/test_playback.py -x`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | PLAY-03 | unit | `python -m pytest tests/test_playback.py::test_playlist_generation -x` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | PLAY-03 | unit | `python -m pytest tests/test_playback.py::test_segment_serving -x` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | PLAY-02 | unit | `python -m pytest tests/test_playback.py::test_availability_gaps -x` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | PLAY-01 | manual | Manual browser test — timeline scrubber interaction | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | PLAY-04 | manual | Manual browser test — live/recording source switching | ❌ W0 | ⬜ pending |
| 04-02-03 | 02 | 1 | PLAY-05 | manual | Manual browser test — playbackRate controls | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_playback.py` — stubs for PLAY-02, PLAY-03 (playlist generation, availability, segment serving)
- [ ] Test fixtures for RecordingSegment creation in test file

*Existing infrastructure covers remaining phase requirements via manual verification.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Timeline scrubber with date/time selection | PLAY-01 | Interactive Svelte component | Open stream page, verify timeline renders, scrub to different times, use date picker |
| Live + recording on same page | PLAY-04 | Browser source switching | Open stream page, verify live view loads, scrub back to recorded time, verify video switches to recording |
| Playback speed 0.5x–8x | PLAY-05 | Browser video element behavior | Open stream page, play recording, change speed via controls, verify playback rate changes |
| Cross-browser playback | PLAY-03 | Requires multiple browsers | Test in Chrome, Firefox, and Safari — verify HLS playback works in all three |
| Gap visualization on timeline | PLAY-02 | Visual rendering | Create gaps in recording, verify timeline shows empty/hatched regions |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
