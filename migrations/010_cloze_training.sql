ALTER TABLE vocabulary_entries
ADD COLUMN part_of_speech TEXT NOT NULL DEFAULT 'other'
    CHECK (part_of_speech IN ('noun', 'verb', 'adjective', 'adverb', 'phrase', 'other'));

CREATE TABLE IF NOT EXISTS vocabulary_cloze_sentences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
    sentence TEXT NOT NULL,
    cloze_order INTEGER NOT NULL,
    UNIQUE (vocabulary_id, cloze_order),
    CHECK (cloze_order BETWEEN 1 AND 3)
);

ALTER TABLE training_sessions
ADD COLUMN training_type TEXT NOT NULL DEFAULT 'definition'
    CHECK (training_type IN ('definition', 'cloze'));

ALTER TABLE training_items
ADD COLUMN question_type TEXT NOT NULL DEFAULT 'definition'
    CHECK (question_type IN ('definition', 'cloze'));

ALTER TABLE training_items
ADD COLUMN prompt_text TEXT;

ALTER TABLE training_answer_options
ADD COLUMN option_text TEXT;

UPDATE training_answer_options
SET option_text = option_definition
WHERE option_text IS NULL;

ALTER TABLE training_incorrect_answers
ADD COLUMN question_type TEXT NOT NULL DEFAULT 'definition'
    CHECK (question_type IN ('definition', 'cloze'));

ALTER TABLE training_incorrect_answers
ADD COLUMN prompt_text TEXT;

ALTER TABLE training_incorrect_answers
ADD COLUMN correct_answer TEXT;

ALTER TABLE training_incorrect_answers
ADD COLUMN selected_answer TEXT;

UPDATE training_incorrect_answers
SET
    correct_answer = correct_definition,
    selected_answer = selected_definition
WHERE correct_answer IS NULL;
