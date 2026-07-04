PRAGMA foreign_keys = OFF;

CREATE TABLE vocabulary_entries_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL,
    definition TEXT NOT NULL,
    definition_key TEXT NOT NULL DEFAULT '',
    context TEXT,
    part_of_speech TEXT NOT NULL DEFAULT 'other'
        CHECK (part_of_speech IN ('noun', 'verb', 'adjective', 'adverb', 'phrase', 'other')),
    frequency_band TEXT
        CHECK (
            frequency_band IS NULL OR frequency_band IN (
                'common',
                'uncommon',
                'rare',
                'very_rare',
                'archaic_or_obsolete',
                'specialized'
            )
        ),
    frequency_note TEXT,
    needs_attention TEXT
        CHECK (needs_attention IS NULL OR length(needs_attention) <= 200),
    confidence_score INTEGER
        CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100),
    confidence_obsolete INTEGER NOT NULL DEFAULT 0
        CHECK (confidence_obsolete IN (0, 1)),
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO vocabulary_entries_new
    (
        id,
        word,
        definition,
        definition_key,
        context,
        part_of_speech,
        frequency_band,
        frequency_note,
        needs_attention,
        confidence_score,
        confidence_obsolete,
        created_by,
        created_at,
        updated_at
    )
SELECT
    id,
    word,
    definition,
    lower(trim(replace(replace(replace(replace(definition, '.', ''), ',', ''), ';', ''), ':', ''))),
    context,
    part_of_speech,
    NULL,
    NULL,
    needs_attention,
    confidence_score,
    confidence_obsolete,
    created_by,
    created_at,
    updated_at
FROM vocabulary_entries;

DROP TABLE vocabulary_entries;
ALTER TABLE vocabulary_entries_new RENAME TO vocabulary_entries;

CREATE UNIQUE INDEX vocabulary_entries_sense_unique_idx
ON vocabulary_entries(lower(word), part_of_speech, definition_key);

PRAGMA foreign_key_check;
PRAGMA foreign_keys = ON;
