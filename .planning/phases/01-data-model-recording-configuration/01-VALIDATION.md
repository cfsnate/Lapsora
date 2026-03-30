---
phase: 1
slug: data-model-recording-configuration
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-30
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend), vitest (frontend) |
| **Config file** | `backend/tests/conftest.py`, `frontend/vitest.config.ts` |
| **Quick run command** | `cd backend && python -m pytest tests/ -x -q` |
| **Full suite command** | `cd backend && python -m pytest tests/ -v && cd ../frontend && npm run test` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/ -x -q`
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-T1 | 01-01 | 1 | REC-02 | unit | `cd backend && python -c "from app.models import Profile, RecordingSegment, ClipExport; print('OK')"` | ✅ | ⬜ pending |
| 01-01-T2 | 01-01 | 1 | REC-02, REC-05 | unit | `cd backend && python -c "from app.schemas import ProfileCreate; p = ProfileCreate(name='t'); assert p.segment_duration_seconds == 600; print('OK')"` | ✅ | ⬜ pending |
| 01-01-T3 | 01-01 | 1 | REC-02, REC-05 | integration | `cd backend && python -m pytest tests/test_profiles.py -x -v` | ✅ | ⬜ pending |
| 01-02-T1 | 01-02 | 1 | REC-02 | type-check | `cd frontend && npx tsc --noEmit` | ✅ | ⬜ pending |
| 01-02-T2 | 01-02 | 1 | REC-02, REC-05 | type-check | `cd frontend && npx svelte-check --threshold error` | ✅ | ⬜ pending |
| 01-02-T3 | 01-02 | 1 | REC-02, REC-05 | manual | Human visual verification of recording UI | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. Recording tests are added to `backend/tests/test_profiles.py` (Plan 01-01, Task 3) using the existing test helpers (`_create_stream`, `_create_profile`) and `conftest.py` fixtures. No separate test file needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Recording toggle UI expands/collapses settings | REC-02 | Browser interaction required | Enable recording toggle, verify settings section appears |
| Schedule configuration persists after restart | REC-05 | Requires app restart cycle | Configure schedule, restart app, verify config persisted |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
