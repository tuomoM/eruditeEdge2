CREATE TABLE IF NOT EXISTS vocabulary_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    author TEXT,
    source_type TEXT NOT NULL DEFAULT 'other',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS vocabulary_sources_name_author_idx
ON vocabulary_sources(name COLLATE NOCASE, author COLLATE NOCASE, source_type);

CREATE TABLE IF NOT EXISTS vocabulary_entry_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES vocabulary_sources(id) ON DELETE CASCADE,
    note TEXT NOT NULL DEFAULT '',
    source_order INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (vocabulary_id, source_order)
);

CREATE INDEX IF NOT EXISTS vocabulary_entry_sources_vocabulary_id_idx
ON vocabulary_entry_sources(vocabulary_id);

CREATE INDEX IF NOT EXISTS vocabulary_entry_sources_source_id_idx
ON vocabulary_entry_sources(source_id);
