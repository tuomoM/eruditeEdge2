ALTER TABLE users ADD COLUMN google_sub TEXT;
ALTER TABLE users ADD COLUMN google_email TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub
    ON users(google_sub)
    WHERE google_sub IS NOT NULL;
