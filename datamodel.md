# Data Model

This document describes the SQLite data model used by eruditeEdge2. It should
be updated whenever a table, column, relationship, constraint, or important
data lifecycle rule changes.

The canonical schema for a new database is in `schema.sql`. Existing databases
are upgraded through the ordered SQL files in `migrations/`.

## Relationship Overview

```text
users
  |--< vocabulary_entries
  |      |--< vocabulary_synonyms
  |      |--< vocabulary_examples
  |      |--< vocabulary_cloze_sentences
  |      `--< vocabulary_domains
  |
  |--< training_sessions
  |      |--< training_items >-- vocabulary_entries
  |      |--< training_answer_options >-- vocabulary_entries
  |      `--< training_incorrect_answers >-- vocabulary_entries
  |
  |--< ai_generation_usage
  |--< invite_codes.created_by
  `--< invite_codes.used_by

access_requests
schema_migrations
```

`<` indicates the many side of a one-to-many relationship.

## Vocabulary Classification

Vocabulary entries use three separate classification concepts:

- `context`: Usage setting or register, such as Academic, Medical, Formal, or
  General. It does not describe the semantic meaning of the word.
- `part_of_speech`: Grammatical classification used by cloze training:
  `noun`, `verb`, `adjective`, `adverb`, `phrase`, or `other`.
- `domains`: Semantic areas represented by the word's meaning, such as
  cognition, communication, power, or rhetoric. An entry may have zero to four
  domains.

These fields must remain independent. For example, a word may have context
`Academic`, part of speech `noun`, and domains `cognition` and `communication`.

## Tables

### `users`

Stores local accounts and optional Google identity information.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `username` | TEXT | Required, unique |
| `password_hash` | TEXT | Required |
| `account_category` | TEXT | Required; `basic`, `trusted`, or `admin`; defaults to `basic` |
| `google_sub` | TEXT | Optional, unique |
| `google_email` | TEXT | Optional |
| `created_at` | TIMESTAMP | Defaults to current timestamp |

### `vocabulary_entries`

Stores the core record for one vocabulary meaning. Vocabulary is global, while
`created_by` records its original creator.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `word` | TEXT | Required |
| `definition` | TEXT | Required |
| `context` | TEXT | Optional usage setting or register |
| `part_of_speech` | TEXT | Required; controlled grammatical value; defaults to `other` |
| `created_by` | INTEGER | Required reference to `users.id` |
| `created_at` | TIMESTAMP | Defaults to current timestamp |
| `updated_at` | TIMESTAMP | Defaults to current timestamp; updated by application writes |

The combination of `word` and `context` is unique.

### `vocabulary_synonyms`

Stores the repeatable synonyms of a vocabulary entry.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `vocabulary_id` | INTEGER | Required reference to `vocabulary_entries.id`; cascades on delete |
| `synonym` | TEXT | Required |

A synonym may appear only once per vocabulary entry.

### `vocabulary_examples`

Stores one to four ordered example sentences.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `vocabulary_id` | INTEGER | Required reference to `vocabulary_entries.id`; cascades on delete |
| `example_sentence` | TEXT | Required |
| `example_order` | INTEGER | Required; 1 through 4 |

Each order position may appear only once per vocabulary entry.

### `vocabulary_cloze_sentences`

Stores up to three ordered cloze prompts. Each sentence is validated by the
application to contain exactly one `____` blank and not reveal the target word.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `vocabulary_id` | INTEGER | Required reference to `vocabulary_entries.id`; cascades on delete |
| `sentence` | TEXT | Required |
| `cloze_order` | INTEGER | Required; 1 through 3 |

Each order position may appear only once per vocabulary entry.

### `vocabulary_domains`

Stores the ordered semantic domains assigned to a vocabulary entry.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `vocabulary_id` | INTEGER | Required reference to `vocabulary_entries.id`; cascades on delete |
| `domain` | TEXT | Required; controlled domain value |
| `domain_order` | INTEGER | Required; 1 through 4 |

A domain and an order position may each appear only once per vocabulary entry.
The allowed domains are:

`emotion`, `attitude`, `cognition`, `communication`, `morality`, `justice`,
`power`, `society`, `status`, `conflict`, `violence`, `time`, `change`,
`certainty`, `perception`, `appearance`, `movement`, `quantity`, `causation`,
`rhetoric`, `literature`, `religion`, and `body`.

The shared application catalog is defined in
`Services/vocabulary_domains.py`. Keep it synchronized with the database
constraints in `schema.sql` and the relevant migration.

### `training_sessions`

Stores one generated quiz and its eventual aggregate result.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `user_id` | INTEGER | Required reference to `users.id` |
| `created_at` | TIMESTAMP | Defaults to current timestamp |
| `training_type` | TEXT | Required; `definition` or `cloze` |
| `submitted_at` | TIMESTAMP | Optional until submitted |
| `score` | INTEGER | Optional until submitted |
| `total` | INTEGER | Optional until submitted |

### `training_items`

Stores the questions selected for a training session.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `training_session_id` | INTEGER | Required reference to `training_sessions.id`; cascades on delete |
| `vocabulary_id` | INTEGER | Required reference to `vocabulary_entries.id` |
| `question_token` | TEXT | Required, unique public answer token |
| `question_type` | TEXT | Required; `definition` or `cloze` |
| `word` | TEXT | Required snapshot |
| `context` | TEXT | Optional snapshot |
| `definition` | TEXT | Required snapshot |
| `prompt_text` | TEXT | Optional; used for cloze prompts |
| `item_order` | INTEGER | Required display order |

A vocabulary entry and an item order may each appear only once in a session.
The word, context, definition, and prompt are copied into the training item so
an existing quiz remains stable when vocabulary data is later edited.

### `training_answer_options`

Stores the generated options for every training question.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `training_session_id` | INTEGER | Required reference to `training_sessions.id`; cascades on delete |
| `question_token` | TEXT | Required reference to `training_items.question_token`; cascades on delete |
| `option_token` | TEXT | Required, unique public answer token |
| `option_vocabulary_id` | INTEGER | Required reference to `vocabulary_entries.id` |
| `option_definition` | TEXT | Required definition snapshot |
| `option_text` | TEXT | Displayed answer snapshot |
| `option_order` | INTEGER | Required display order |

An option vocabulary entry and an option order may each appear only once per
question. Cloze options are selected from the complete vocabulary pool while
matching the question's part of speech.

### `training_incorrect_answers`

Stores review data for incorrectly answered questions after submission.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `training_session_id` | INTEGER | Required reference to `training_sessions.id`; cascades on delete |
| `vocabulary_id` | INTEGER | Required reference to `vocabulary_entries.id` |
| `question_type` | TEXT | Required; `definition` or `cloze` |
| `word` | TEXT | Required snapshot |
| `prompt_text` | TEXT | Optional prompt snapshot |
| `correct_definition` | TEXT | Required snapshot |
| `selected_definition` | TEXT | Optional snapshot |
| `correct_answer` | TEXT | Correct displayed answer |
| `selected_answer` | TEXT | Selected displayed answer |

### `ai_generation_usage`

Tracks daily AI generation quota consumption per user.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `user_id` | INTEGER | Required reference to `users.id`; cascades on delete |
| `generation_date` | TEXT | Required application date |
| `generation_count` | INTEGER | Required, non-negative; defaults to 0 |

There is one row per user and generation date.

### `invite_codes`

Stores invitation codes and their optional redemption information.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `code` | TEXT | Required, unique |
| `created_by` | INTEGER | Required reference to `users.id` |
| `created_at` | TIMESTAMP | Defaults to current timestamp |
| `expires_at` | TEXT | Required expiration timestamp |
| `used_by` | INTEGER | Optional reference to `users.id` |
| `used_at` | TEXT | Optional redemption timestamp |

### `access_requests`

Stores public requests for access.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `name` | TEXT | Required |
| `email` | TEXT | Required, unique |
| `message` | TEXT | Required |
| `ip_address` | TEXT | Required |
| `created_at` | TIMESTAMP | Defaults to current timestamp |

### `schema_migrations`

Created and maintained by the Flask `migrate` command rather than
`schema.sql`.

| Column | Type | Rules |
| --- | --- | --- |
| `filename` | TEXT | Primary key; migration filename |
| `applied_at` | TIMESTAMP | Defaults to current timestamp |

It records which files in `migrations/` have been applied or stamped.

## Deletion Rules

- Deleting a vocabulary entry cascades to synonyms, examples, cloze sentences,
  and domains.
- Training records reference vocabulary entries without cascading. The
  application removes affected training sessions before deleting all
  vocabulary created by a user.
- Deleting a training session cascades to its items, options, and incorrect
  answers.
- Deleting a user cascades to AI usage rows. Other user relationships require
  explicit application handling.
- SQLite foreign key enforcement is enabled for every application connection
  with `PRAGMA foreign_keys = ON`.

## Schema Changes

When changing the data model:

1. Update `schema.sql` for newly initialized databases.
2. Add the next numbered migration for existing databases.
3. Add its detection marker to `MIGRATION_MARKERS` in `cli.py`.
4. Update repositories, services, validation, and tests.
5. Update this document in the same change.
6. Run `flask --app app migrate` locally and run the full test suite.

Production upgrades use:

```bash
flask --app app migrate
```
