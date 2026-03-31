-- Migration 025: Reset all segment durations to NULL so scanner re-probes.
-- Fixes incorrect durations from when the scanner used mtime-based stability
-- (which caused premature ffprobe on still-writing files).
-- Segments stay in the DB (not deleted) — only duration/end_time are cleared.

UPDATE recording_segments SET duration_seconds = NULL, end_time = NULL;
