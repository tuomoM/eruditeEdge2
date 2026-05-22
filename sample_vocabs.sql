INSERT OR IGNORE INTO users (username, password_hash)
VALUES ('sample_user', 'sample-password-hash');

INSERT OR IGNORE INTO vocabulary_entries (word, definition, context, created_by)
VALUES
    (
        'Ubiquitous',
        'Present, appearing, or found everywhere.',
        'General',
        (SELECT id FROM users WHERE username = 'sample_user')
    ),
    (
        'curfew',
        'A rule requiring people to remain indoors during specific hours.',
        'Legal/Social',
        (SELECT id FROM users WHERE username = 'sample_user')
    ),
    (
        'myopic',
        'Lacking imagination, foresight, or intellectual insight.',
        'General/Medical',
        (SELECT id FROM users WHERE username = 'sample_user')
    ),
    (
        'indignation',
        'Anger or annoyance provoked by something perceived as unfair.',
        'Emotional/Formal',
        (SELECT id FROM users WHERE username = 'sample_user')
    ),
    (
        'predillection',
        'A preference or special liking for something.',
        'Formal',
        (SELECT id FROM users WHERE username = 'sample_user')
    );

INSERT OR IGNORE INTO vocabulary_synonyms (vocabulary_id, synonym)
SELECT id, 'omnipresent' FROM vocabulary_entries WHERE word = 'Ubiquitous' AND context = 'General';
INSERT OR IGNORE INTO vocabulary_synonyms (vocabulary_id, synonym)
SELECT id, 'pervasive' FROM vocabulary_entries WHERE word = 'Ubiquitous' AND context = 'General';
INSERT OR IGNORE INTO vocabulary_synonyms (vocabulary_id, synonym)
SELECT id, 'restriction' FROM vocabulary_entries WHERE word = 'curfew' AND context = 'Legal/Social';
INSERT OR IGNORE INTO vocabulary_synonyms (vocabulary_id, synonym)
SELECT id, 'deadline' FROM vocabulary_entries WHERE word = 'curfew' AND context = 'Legal/Social';
INSERT OR IGNORE INTO vocabulary_synonyms (vocabulary_id, synonym)
SELECT id, 'short-sighted' FROM vocabulary_entries WHERE word = 'myopic' AND context = 'General/Medical';
INSERT OR IGNORE INTO vocabulary_synonyms (vocabulary_id, synonym)
SELECT id, 'narrow-minded' FROM vocabulary_entries WHERE word = 'myopic' AND context = 'General/Medical';
INSERT OR IGNORE INTO vocabulary_synonyms (vocabulary_id, synonym)
SELECT id, 'resentment' FROM vocabulary_entries WHERE word = 'indignation' AND context = 'Emotional/Formal';
INSERT OR IGNORE INTO vocabulary_synonyms (vocabulary_id, synonym)
SELECT id, 'outrage' FROM vocabulary_entries WHERE word = 'indignation' AND context = 'Emotional/Formal';
INSERT OR IGNORE INTO vocabulary_synonyms (vocabulary_id, synonym)
SELECT id, 'preference' FROM vocabulary_entries WHERE word = 'predillection' AND context = 'Formal';
INSERT OR IGNORE INTO vocabulary_synonyms (vocabulary_id, synonym)
SELECT id, 'fondness' FROM vocabulary_entries WHERE word = 'predillection' AND context = 'Formal';

INSERT OR IGNORE INTO vocabulary_examples (vocabulary_id, example_sentence, example_order)
SELECT id, 'Smartphones have become ubiquitous in modern life.', 1
FROM vocabulary_entries WHERE word = 'Ubiquitous' AND context = 'General';
INSERT OR IGNORE INTO vocabulary_examples (vocabulary_id, example_sentence, example_order)
SELECT id, 'The city imposed a curfew after the storm.', 1
FROM vocabulary_entries WHERE word = 'curfew' AND context = 'Legal/Social';
INSERT OR IGNORE INTO vocabulary_examples (vocabulary_id, example_sentence, example_order)
SELECT id, 'The plan was criticized as myopic because it ignored future costs.', 1
FROM vocabulary_entries WHERE word = 'myopic' AND context = 'General/Medical';
INSERT OR IGNORE INTO vocabulary_examples (vocabulary_id, example_sentence, example_order)
SELECT id, 'She felt indignation at the unfair accusation.', 1
FROM vocabulary_entries WHERE word = 'indignation' AND context = 'Emotional/Formal';
INSERT OR IGNORE INTO vocabulary_examples (vocabulary_id, example_sentence, example_order)
SELECT id, 'He had a predillection for old maps and rare books.', 1
FROM vocabulary_entries WHERE word = 'predillection' AND context = 'Formal';
