CREATE TABLE vocabulary_word_lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    source_url TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE vocabulary_word_list_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_list_id INTEGER NOT NULL REFERENCES vocabulary_word_lists(id) ON DELETE CASCADE,
    word TEXT NOT NULL COLLATE NOCASE,
    UNIQUE (word_list_id, word)
);

CREATE INDEX vocabulary_word_list_entries_word_idx
ON vocabulary_word_list_entries(word COLLATE NOCASE);

CREATE TABLE vocabulary_entry_word_lists (
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
    word_list_id INTEGER NOT NULL REFERENCES vocabulary_word_lists(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (vocabulary_id, word_list_id)
);

CREATE INDEX vocabulary_entry_word_lists_word_list_idx
ON vocabulary_entry_word_lists(word_list_id, vocabulary_id);
