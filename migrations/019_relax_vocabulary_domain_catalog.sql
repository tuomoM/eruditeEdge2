PRAGMA foreign_keys = OFF;

CREATE TABLE vocabulary_domains_relaxed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    domain_order INTEGER NOT NULL CHECK (domain_order BETWEEN 1 AND 4),
    UNIQUE (vocabulary_id, domain),
    UNIQUE (vocabulary_id, domain_order)
);

INSERT INTO vocabulary_domains_relaxed
    (id, vocabulary_id, domain, domain_order)
SELECT id, vocabulary_id, domain, domain_order
FROM vocabulary_domains;

DROP TABLE vocabulary_domains;

ALTER TABLE vocabulary_domains_relaxed
RENAME TO vocabulary_domains;

PRAGMA foreign_key_check;
PRAGMA foreign_keys = ON;
