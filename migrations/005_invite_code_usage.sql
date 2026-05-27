ALTER TABLE invite_codes ADD COLUMN used_by INTEGER REFERENCES users(id);
ALTER TABLE invite_codes ADD COLUMN used_at TEXT;
