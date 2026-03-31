-- Add per-profile permission flags to user_profile_access
ALTER TABLE user_profile_access ADD COLUMN can_view BOOLEAN NOT NULL DEFAULT 1;
ALTER TABLE user_profile_access ADD COLUMN can_export BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE user_profile_access ADD COLUMN can_timelapse BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE user_profile_access ADD COLUMN can_manage BOOLEAN NOT NULL DEFAULT 0;

-- Add per-profile permission flags to group_profile_access
ALTER TABLE group_profile_access ADD COLUMN can_view BOOLEAN NOT NULL DEFAULT 1;
ALTER TABLE group_profile_access ADD COLUMN can_export BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE group_profile_access ADD COLUMN can_timelapse BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE group_profile_access ADD COLUMN can_manage BOOLEAN NOT NULL DEFAULT 0;

-- User-to-group membership (for local and OIDC users)
CREATE TABLE IF NOT EXISTS user_group_membership (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    UNIQUE(user_id, group_id)
);
