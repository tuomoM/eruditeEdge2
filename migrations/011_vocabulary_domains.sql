CREATE TABLE IF NOT EXISTS vocabulary_domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
    domain TEXT NOT NULL
        CHECK (
            domain IN (
                'emotion',
                'attitude',
                'cognition',
                'communication',
                'morality',
                'justice',
                'power',
                'society',
                'status',
                'conflict',
                'violence',
                'time',
                'change',
                'certainty',
                'perception',
                'appearance',
                'movement',
                'quantity',
                'causation',
                'rhetoric',
                'literature',
                'religion',
                'body'
            )
        ),
    domain_order INTEGER NOT NULL CHECK (domain_order BETWEEN 1 AND 4),
    UNIQUE (vocabulary_id, domain),
    UNIQUE (vocabulary_id, domain_order)
);
