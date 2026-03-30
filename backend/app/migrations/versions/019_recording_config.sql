-- Recording configuration on profiles
ALTER TABLE profiles ADD COLUMN recording_enabled INTEGER NOT NULL DEFAULT 0;
ALTER TABLE profiles ADD COLUMN recording_mode TEXT NOT NULL DEFAULT 'always';
ALTER TABLE profiles ADD COLUMN recording_start_time TEXT;
ALTER TABLE profiles ADD COLUMN recording_end_time TEXT;
ALTER TABLE profiles ADD COLUMN recording_sun_offset_minutes INTEGER NOT NULL DEFAULT 0;
ALTER TABLE profiles ADD COLUMN recording_sun_events TEXT NOT NULL DEFAULT '';
ALTER TABLE profiles ADD COLUMN segment_duration_seconds INTEGER NOT NULL DEFAULT 600;
ALTER TABLE profiles ADD COLUMN recording_storage_path TEXT;
ALTER TABLE profiles ADD COLUMN recording_days TEXT NOT NULL DEFAULT '';

-- Recording segments table
CREATE TABLE IF NOT EXISTS recording_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    duration_seconds REAL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    codec TEXT,
    resolution_width INTEGER,
    resolution_height INTEGER,
    protected INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_recording_segments_profile_start
    ON recording_segments(profile_id, start_time);

-- Clip exports table
CREATE TABLE IF NOT EXISTS clip_exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    file_path TEXT,
    file_size INTEGER,
    format TEXT NOT NULL DEFAULT 'mp4',
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    duration_seconds REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_clip_exports_profile
    ON clip_exports(profile_id);
