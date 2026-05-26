ALTER TABLE training_sessions ADD COLUMN submitted_at TIMESTAMP;
ALTER TABLE training_sessions ADD COLUMN score INTEGER;
ALTER TABLE training_sessions ADD COLUMN total INTEGER;

ALTER TABLE training_items ADD COLUMN question_token TEXT;
ALTER TABLE training_items ADD COLUMN word TEXT;
ALTER TABLE training_items ADD COLUMN context TEXT;
ALTER TABLE training_items ADD COLUMN definition TEXT;

UPDATE training_items
SET
    question_token = 'legacy-training-item-' || id,
    word = (
        SELECT vocabulary_entries.word
        FROM vocabulary_entries
        WHERE vocabulary_entries.id = training_items.vocabulary_id
    ),
    context = (
        SELECT vocabulary_entries.context
        FROM vocabulary_entries
        WHERE vocabulary_entries.id = training_items.vocabulary_id
    ),
    definition = (
        SELECT vocabulary_entries.definition
        FROM vocabulary_entries
        WHERE vocabulary_entries.id = training_items.vocabulary_id
    )
WHERE question_token IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_training_items_question_token
    ON training_items(question_token);

CREATE TABLE IF NOT EXISTS training_answer_options (
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

CREATE TABLE IF NOT EXISTS training_incorrect_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    training_session_id INTEGER NOT NULL REFERENCES training_sessions(id) ON DELETE CASCADE,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id),
    word TEXT NOT NULL,
    correct_definition TEXT NOT NULL,
    selected_definition TEXT
);

UPDATE training_sessions
SET
    submitted_at = CURRENT_TIMESTAMP,
    score = 0,
    total = (
        SELECT COUNT(*)
        FROM training_items
        WHERE training_items.training_session_id = training_sessions.id
    )
WHERE submitted_at IS NULL
    AND EXISTS (
        SELECT 1
        FROM training_items
        WHERE training_items.training_session_id = training_sessions.id
    );
