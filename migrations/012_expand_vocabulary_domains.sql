CREATE TABLE vocabulary_domains_expanded (
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
                'quality',
                'relation',
                'degree',
                'movement',
                'quantity',
                'causation',
                'judgment',
                'reasoning',
                'truth',
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

INSERT INTO vocabulary_domains_expanded
    (id, vocabulary_id, domain, domain_order)
SELECT id, vocabulary_id, domain, domain_order
FROM vocabulary_domains;

DROP TABLE vocabulary_domains;

ALTER TABLE vocabulary_domains_expanded
RENAME TO vocabulary_domains;
