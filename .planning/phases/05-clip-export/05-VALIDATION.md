---
phase: 5
slug: clip-export
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-30
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | none — invoked directly |
| **Quick run command** | `cd backend && python -m pytest tests/test_exports.py -x` |
| **Full suite command** | `cd backend && python -m pytest tests/ -x` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/test_exports.py -x`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | EXPRT-01 | unit | `python -m pytest tests/test_exports.py::test_create_export -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | EXPRT-01 | unit | `python -m pytest tests/test_exports.py::test_segment_overlap_query -x` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | EXPRT-02 | unit | `python -m pytest tests/test_exports.py::test_quality_presets -x` | ❌ W0 | ⬜ pending |
| 05-01-04 | 01 | 1 | EXPRT-02 | unit | `python -m pytest tests/test_exports.py::test_resolution_conditional -x` | ❌ W0 | ⬜ pending |
| 05-01-05 | 01 | 1 | EXPRT-03 | unit | `python -m pytest tests/test_exports.py::test_independent_queue -x` | ❌ W0 | ⬜ pending |
| 05-01-06 | 01 | 1 | EXPRT-03 | unit | `python -m pytest tests/test_exports.py::test_restore_pending -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | EXPRT-01 | manual | Manual browser test — timeline drag-select and export dialog | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 1 | EXPRT-02 | manual | Manual browser test — quality/resolution selector | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_exports.py` — stubs for EXPRT-01, EXPRT-02, EXPRT-03
- [ ] No framework install needed — pytest already in use

*Existing infrastructure covers remaining phase requirements via manual verification.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Timeline drag-to-select range | EXPRT-01 | Interactive Svelte component | Open playback page, drag on timeline to select range, verify start/end markers appear |
| Export dialog with editable times | EXPRT-01 | UI interaction | Click Export Clip, verify dialog pre-fills from timeline selection, edit times |
| Quality/resolution selector | EXPRT-02 | UI dropdown behavior | Select High/Medium/Low quality, verify resolution dropdown appears |
| Export download from /exports page | EXPRT-01 | End-to-end with real files | Submit export, wait for completion, verify download works |
| Concurrent export + timelapse | EXPRT-03 | Requires two running processes | Start a timelapse generation and export simultaneously, verify neither blocks |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
