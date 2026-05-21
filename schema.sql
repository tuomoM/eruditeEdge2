CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE vocabulary_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL,
    definition TEXT NOT NULL,
    context TEXT,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (word, context)
);

CREATE TABLE vocabulary_synonyms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
    synonym TEXT NOT NULL,
    UNIQUE (vocabulary_id, synonym)
);

CREATE TABLE vocabulary_examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
    example_sentence TEXT NOT NULL,
    example_order INTEGER NOT NULL,
    CHECK (example_order BETWEEN 1 AND 4),
    UNIQUE (vocabulary_id, example_order)
);
