-- Migration 022: Reduce default segment duration from 600s to 300s
-- Existing profiles at the old default of 600 are updated to 300.
-- Profiles with custom values are left unchanged.

UPDATE profiles
SET segment_duration_seconds = 300
WHERE segment_duration_seconds = 600;
