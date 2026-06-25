ALTER TABLE vocabulary_entries
ADD COLUMN needs_attention TEXT
    CHECK (needs_attention IS NULL OR length(needs_attention) <= 200);

ALTER TABLE vocabulary_entries
ADD COLUMN confidence_score INTEGER
    CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100);

ALTER TABLE vocabulary_entries
ADD COLUMN confidence_obsolete INTEGER NOT NULL DEFAULT 0
    CHECK (confidence_obsolete IN (0, 1));
