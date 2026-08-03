ALTER TABLE vocabulary_entries
ADD COLUMN gre_rating TEXT
    CHECK (gre_rating IS NULL OR gre_rating IN ('high', 'medium', 'low', 'unlikely'));
