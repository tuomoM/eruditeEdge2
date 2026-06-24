CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    account_category TEXT NOT NULL DEFAULT 'basic'
        CHECK (account_category IN ('basic', 'trusted', 'admin')),
    google_sub TEXT UNIQUE,
    google_email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE vocabulary_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL,
    definition TEXT NOT NULL,
    context TEXT,
    part_of_speech TEXT NOT NULL DEFAULT 'other'
        CHECK (part_of_speech IN ('noun', 'verb', 'adjective', 'adverb', 'phrase', 'other')),
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

CREATE TABLE vocabulary_cloze_sentences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
    sentence TEXT NOT NULL,
    cloze_order INTEGER NOT NULL,
    UNIQUE (vocabulary_id, cloze_order),
    CHECK (cloze_order BETWEEN 1 AND 3)
);

CREATE TABLE vocabulary_domains (
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

CREATE TABLE training_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    training_type TEXT NOT NULL DEFAULT 'definition'
        CHECK (training_type IN ('definition', 'cloze')),
    submitted_at TIMESTAMP,
    score INTEGER,
    total INTEGER
);

CREATE TABLE training_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    training_session_id INTEGER NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id),
    question_token TEXT NOT NULL UNIQUE,
    question_type TEXT NOT NULL DEFAULT 'definition'
        CHECK (question_type IN ('definition', 'cloze')),
    word TEXT NOT NULL,
    context TEXT,
    definition TEXT NOT NULL,
    prompt_text TEXT,
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
    option_text TEXT,
    option_order INTEGER NOT NULL,
    UNIQUE (question_token, option_vocabulary_id),
    UNIQUE (question_token, option_order)
);

CREATE TABLE training_incorrect_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    training_session_id INTEGER NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id),
    question_type TEXT NOT NULL DEFAULT 'definition'
        CHECK (question_type IN ('definition', 'cloze')),
    word TEXT NOT NULL,
    prompt_text TEXT,
    correct_definition TEXT NOT NULL,
    selected_definition TEXT,
    correct_answer TEXT,
    selected_answer TEXT
);

CREATE TABLE ai_generation_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    generation_date TEXT NOT NULL,
    generation_count INTEGER NOT NULL DEFAULT 0
        CHECK (generation_count >= 0),
    UNIQUE (user_id, generation_date)
);

CREATE TABLE invite_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL,
    used_by INTEGER REFERENCES users(id),
    used_at TEXT
);

CREATE TABLE access_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    message TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
