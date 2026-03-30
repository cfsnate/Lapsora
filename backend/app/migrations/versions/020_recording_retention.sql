-- Per-profile recording retention override
ALTER TABLE profiles ADD COLUMN recording_retention_days INTEGER;
