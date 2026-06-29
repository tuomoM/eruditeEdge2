ALTER TABLE vocabulary_synonyms
ADD COLUMN linked_vocabulary_id INTEGER REFERENCES vocabulary_entries(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS vocabulary_synonyms_linked_vocabulary_id_idx
ON vocabulary_synonyms(linked_vocabulary_id);

CREATE INDEX IF NOT EXISTS vocabulary_synonyms_synonym_nocase_idx
ON vocabulary_synonyms(synonym COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS background_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'failed')),
    payload TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0
        CHECK (attempts >= 0),
    last_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS background_jobs_status_type_idx
ON background_jobs(status, job_type, created_at);
