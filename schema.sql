CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    account_category TEXT NOT NULL DEFAULT 'basic'
        CHECK (account_category IN ('basic', 'trusted', 'admin')),
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

CREATE TABLE training_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMP,
    score INTEGER,
    total INTEGER
);

CREATE TABLE training_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    training_session_id INTEGER NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id),
    question_token TEXT NOT NULL UNIQUE,
    word TEXT NOT NULL,
    context TEXT,
    definition TEXT NOT NULL,
    item_order INTEGER NOT NULL,
    UNIQUE (training_session_id, vocabulary_id),
    UNIQUE (training_session_id, item_order)
);

CREATE TABLE training_answer_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    training_session_id INTEGER NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
    question_token TEXT NOT NULL REFERENCES training_items(question_token) ON DELETE CASCADE,
    option_token TEXT NOT NULL UNIQUE,
    option_vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id),
    option_definition TEXT NOT NULL,
    option_order INTEGER NOT NULL,
    UNIQUE (question_token, option_vocabulary_id),
    UNIQUE (question_token, option_order)
);

CREATE TABLE training_incorrect_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    training_session_id INTEGER NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id),
    word TEXT NOT NULL,
    correct_definition TEXT NOT NULL,
    selected_definition TEXT
);

CREATE TABLE ai_generation_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    generation_date TEXT NOT NULL,
    generation_count INTEGER NOT NULL DEFAULT 0
        CHECK (generation_count >= 0),
    UNIQUE (user_id, generation_date)
);
