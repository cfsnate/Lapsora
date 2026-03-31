-- Migration 024: Re-clear recording segments so scanner re-registers them
-- with correct durations. Previous scanner used mtime-based stability check
-- which caused premature ffprobe on in-progress files, recording only 2-3
-- minutes of content instead of the full segment duration.

DELETE FROM recording_segments;
