-- Migration 023: Clear recording segments so scanner re-registers them
-- with correct UTC timestamps (previous code used .replace(tzinfo=UTC)
-- which labeled local-time filenames as UTC without converting).

DELETE FROM recording_segments;
