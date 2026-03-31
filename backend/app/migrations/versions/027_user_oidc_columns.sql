ALTER TABLE users ADD COLUMN oidc_provider TEXT;
ALTER TABLE users ADD COLUMN oidc_subject TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_oidc
    ON users (oidc_provider, oidc_subject)
    WHERE oidc_provider IS NOT NULL AND oidc_subject IS NOT NULL;
