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
  |      |--< vocabulary_domains
  |      `--< vocabulary_entry_sources >-- vocabulary_sources
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

- `context`: Semicolon-separated usage context labels. AI should choose at
  least one register label from `Informal`, `Formal`, `Literary`, `Technical`,
  `Archaic`, and `Dialectal`, plus zero or more usage-domain labels from
  `Academic`, `Business`, `Legal`, `Medical`, `Biology`, `Science`,
  `Philosophy`, `Religion`, `Military`, and `Geography`. It does not describe
  the semantic meaning of the word. `General` is no longer used as a fallback.
- `part_of_speech`: Grammatical classification used by cloze training:
  `noun`, `verb`, `adjective`, `adverb`, `phrase`, or `other`.
- `frequency_band`: How common this exact word sense is: `common`,
  `uncommon`, `rare`, `very_rare`, `archaic_or_obsolete`, or `specialized`.
- `frequency_note`: Optional short explanation of the frequency or register.
- `domains`: Semantic areas represented by the word's meaning, such as
  cognition, communication, power, or rhetoric. An entry may have zero to four
  domains.
- `needs_attention`: Optional AI explanation of uncertainty requiring admin
  review. It is assessment metadata, not a domain.
- `confidence_score`: AI confidence from 0 to 100 for the generated entry.
  Manual edits preserve the score but mark it obsolete.
- `sources`: Optional places where the user noticed the word, such as a book,
  article, film, or conversation. Sources are not required for vocabulary
  creation and may be omitted entirely.

These fields must remain independent. For example, a word may have context
`Formal; Academic`, part of speech `noun`, frequency `uncommon`, and domains
`cognition` and `communication`.

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
`created_by` records its original creator for ownership and administrative
logic. Public list/detail views must not display creator identity.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `word` | TEXT | Required |
| `definition` | TEXT | Required |
| `definition_key` | TEXT | Required normalized definition used for sense uniqueness; internal only |
| `context` | TEXT | Optional usage setting or register |
| `part_of_speech` | TEXT | Required; controlled grammatical value; defaults to `other` |
| `frequency_band` | TEXT | Optional controlled frequency value |
| `frequency_note` | TEXT | Optional frequency or register explanation |
| `needs_attention` | TEXT | Optional AI review explanation; maximum 200 characters |
| `confidence_score` | INTEGER | Optional AI confidence score; 0 through 100 |
| `confidence_obsolete` | INTEGER | Required boolean value; defaults to 0 |
| `created_by` | INTEGER | Required reference to `users.id` |
| `created_at` | TIMESTAMP | Defaults to current timestamp |
| `updated_at` | TIMESTAMP | Defaults to current timestamp; updated by application writes |

The application supports multiple entries with the same spelling when they are
different senses, such as noun and verb meanings of the same word. Duplicate
senses are prevented by a unique index on `lower(word)`, `part_of_speech`, and
`definition_key`.

AI generation may receive an optional usage clue, such as a sentence with the
target word marked in parentheses or a short hint like `a`, `noun`, or
`riding`. The generated entry should describe the sense implied by that clue.
AI generation returns one primary domain first, plus optional secondary and
tertiary domains only when they are clearly represented by the meaning. It must
not pad weakly related domains just to fill the list. It also returns a
frequency band and optional note for the exact sense. A manual vocabulary or
maintenance edit sets `confidence_obsolete` to 1 when a confidence score exists.
An AI maintenance refresh replaces the assessment and resets
`confidence_obsolete` to 0.

### `vocabulary_synonyms`

Stores the repeatable synonyms of a vocabulary entry.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `vocabulary_id` | INTEGER | Required reference to `vocabulary_entries.id`; cascades on delete |
| `linked_vocabulary_id` | INTEGER | Optional reference to the vocabulary entry represented by this synonym; set to null on delete |
| `synonym` | TEXT | Required |

A synonym may appear only once per vocabulary entry. Synonym links are created
by background maintenance, not during the user-facing creation/edit flow. When
a synonym links to another vocabulary entry, the detail page renders it as a
navigation link and the reverse synonym is maintained where missing. When a
synonym link is newly created, a follow-up maintenance job may generate
contrastive cloze prompts for the linked synonym graph.

### `background_jobs`

Stores pending, running, and failed maintenance jobs. Successful jobs are
deleted after completion so this table does not grow indefinitely. Current
maintenance job types include `link_vocabulary_synonyms` and
`generate_synonym_net_cloze`; the latter replaces the cloze sentences of every
entry in a linked synonym graph only after the AI response validates for the
complete graph.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `job_type` | TEXT | Required |
| `status` | TEXT | Required; one of `pending`, `running`, `failed`; defaults to `pending` |
| `payload` | TEXT | Required JSON payload |
| `attempts` | INTEGER | Required; defaults to 0 |
| `last_error` | TEXT | Optional failure detail |
| `created_at` | TIMESTAMP | Defaults to current timestamp |
| `updated_at` | TIMESTAMP | Defaults to current timestamp; updated by job state changes |

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
For linked synonym graphs, background AI maintenance can replace these rows
with contrastive prompts that distinguish nearby meanings.

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
`certainty`, `perception`, `appearance`, `quality`, `relation`, `degree`,
`movement`, `quantity`, `causation`, `judgment`, `reasoning`, `truth`,
`rhetoric`, `literature`, `religion`, and `body`.

The shared application catalog is defined in
`Services/vocabulary_domains.py`. Keep it synchronized with the database
constraints in `schema.sql` and the relevant migration.

### `vocabulary_sources`

Stores reusable source records, such as a book, article, film, or conversation
where vocabulary was encountered. Source records are shared by content and do
not store creator identity.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `name` | TEXT | Required source title or name |
| `author` | TEXT | Optional author, creator, speaker, or publication |
| `source_type` | TEXT | Required; defaults to `other` |
| `created_at` | TIMESTAMP | Defaults to current timestamp |

The application reuses an existing source when `name`, `author`, and
`source_type` match case-insensitively. The current allowed source types are
`book`, `article`, `film`, `conversation`, and `other`.

### `vocabulary_entry_sources`

Stores the optional many-to-many relationship between vocabulary entries and
sources. A vocabulary entry may have zero sources, one source, or many sources.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `vocabulary_id` | INTEGER | Required reference to `vocabulary_entries.id`; cascades on delete |
| `source_id` | INTEGER | Required reference to `vocabulary_sources.id`; cascades on delete |
| `note` | TEXT | Optional location or note; defaults to empty text |
| `source_order` | INTEGER | Required display order |
| `created_at` | TIMESTAMP | Defaults to current timestamp |

Each source order position may appear only once per vocabulary entry. Source
attachments are entered manually; AI generation does not invent sources.
Neither `vocabulary_sources` nor `vocabulary_entry_sources` stores the user who
added the source, preserving the application’s identity-minimization rule.
The user-facing multiline form uses `Title; Author; Location or note` as its
preferred format. The parser also accepts the earlier `Title | Author | Note`
format for compatibility.

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

### `vocabulary_maintenance_runs`

Stores admin-created categorization reassessment runs. A run freezes its
selection filter, taxonomy snapshot, frequency rubric, prompt/schema versions,
AI model, and budget estimates before any AI processing happens. Creating or
processing a run does not modify production vocabulary values.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `name` | TEXT | Required admin label |
| `status` | TEXT | Required run state; starts as `ready` for CLI-created runs |
| `selection_filter_json` | TEXT | Required frozen JSON selection criteria |
| `selected_count` | INTEGER | Required materialized item count |
| `taxonomy_snapshot_json` | TEXT | Required frozen domain/context taxonomy |
| `frequency_rubric_snapshot_json` | TEXT | Required frozen frequency rubric |
| `prompt_template_version` | TEXT | Required prompt version |
| `prompt_template_hash` | TEXT | Required prompt content hash |
| `response_schema_version` | TEXT | Required AI response schema version |
| `validator_version` | TEXT | Required semantic validator version |
| `ai_model` | TEXT | Required maintenance model name |
| `max_items` | INTEGER | Optional item cap |
| `max_estimated_cost` | REAL | Optional estimated cost ceiling |
| `estimated_input_tokens` | INTEGER | Required estimate |
| `estimated_output_tokens` | INTEGER | Required estimate |
| `actual_input_tokens` | INTEGER | Required; starts at 0 |
| `actual_output_tokens` | INTEGER | Required; starts at 0 |
| `actual_cost` | REAL | Required; starts at 0 |
| `created_by` | INTEGER | Optional reference to `users.id` |
| `created_at` | TIMESTAMP | Defaults to current timestamp |
| `started_at` | TIMESTAMP | Optional processing start |
| `completed_at` | TIMESTAMP | Optional processing completion |
| `promoted_at` | TIMESTAMP | Optional promotion timestamp |
| `error_summary` | TEXT | Optional run failure summary |

### `vocabulary_maintenance_items`

Stores one materialized vocabulary entry snapshot inside a maintenance run plus
any generated proposal and review state. The snapshot hash is later used for
conflict-aware promotion.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `run_id` | INTEGER | Required reference to `vocabulary_maintenance_runs.id`; cascades on delete |
| `vocabulary_id` | INTEGER | Required reference to `vocabulary_entries.id`; cascades on delete |
| `item_status` | TEXT | Required item state; starts as `pending` |
| `source_snapshot_json` | TEXT | Required frozen source vocabulary snapshot |
| `source_snapshot_hash` | TEXT | Required SHA-256 hash of the snapshot |
| `source_updated_at` | TIMESTAMP | Production `updated_at` captured at selection time |
| `proposed_context` | TEXT | Optional generated proposal |
| `proposed_frequency_band` | TEXT | Optional generated proposal |
| `proposed_frequency_note` | TEXT | Optional generated proposal |
| `proposed_domains_json` | TEXT | Optional ordered domain proposal |
| `proposed_needs_attention` | TEXT | Optional review warning |
| `model_confidence` | INTEGER | Optional AI confidence, 0 through 100 |
| `review_priority` | INTEGER | Optional application-computed review priority |
| `rationale` | TEXT | Optional model rationale |
| `alternate_domains_json` | TEXT | Optional alternate domain candidates |
| `needs_sense_review` | INTEGER | Required boolean flag |
| `sense_note` | TEXT | Optional sense ambiguity note |
| `raw_response_excerpt` | TEXT | Optional audit excerpt |
| `parsed_response_json` | TEXT | Optional parsed AI response |
| `validation_errors_json` | TEXT | Optional validation errors |
| `failure_type` | TEXT | Optional classified processing failure |
| `attempts` | INTEGER | Required processing attempt count |
| `claimed_by` | TEXT | Optional worker id |
| `claimed_at` | TIMESTAMP | Optional claim time |
| `lease_expires_at` | TIMESTAMP | Optional claim lease expiry |
| `generated_at` | TIMESTAMP | Optional generation time |
| `reviewed_by` | INTEGER | Optional reference to `users.id` |
| `reviewed_at` | TIMESTAMP | Optional review time |
| `rejection_note` | TEXT | Optional admin rejection note |
| `promoted_at` | TIMESTAMP | Optional item promotion timestamp |
| `created_at` | TIMESTAMP | Defaults to current timestamp |

Each `(run_id, vocabulary_id)` pair is unique.

### `vocabulary_maintenance_promotions`

Stores audit records for explicit promotion and later rollback of accepted
maintenance proposals.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `run_id` | INTEGER | Required reference to `vocabulary_maintenance_runs.id`; cascades on delete |
| `item_id` | INTEGER | Required reference to `vocabulary_maintenance_items.id`; cascades on delete |
| `vocabulary_id` | INTEGER | Required reference to `vocabulary_entries.id`; cascades on delete |
| `before_json` | TEXT | Required production values before promotion |
| `after_json` | TEXT | Required promoted values |
| `promoted_by` | INTEGER | Optional reference to `users.id` |
| `promoted_at` | TIMESTAMP | Defaults to current timestamp |
| `rolled_back_by` | INTEGER | Optional reference to `users.id` |
| `rolled_back_at` | TIMESTAMP | Optional rollback timestamp |

### `vocabulary_domain_model_proposals`

Stores AI-generated proposals for a revised semantic domain model. These
records are taxonomy candidates only: they do not modify `vocabulary_domains`
or production vocabulary entries. The proposal should keep semantic domains
separate from context labels and include graph edges that can later support
semantic navigation.

The latest proposal with status `accepted` is the active domain catalog for new
AI vocabulary generation, manual domain validation, and admin domain controls.
If no proposal is accepted, the application falls back to the built-in domain
catalog.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | INTEGER | Primary key, autoincrement |
| `name` | TEXT | Required admin label |
| `status` | TEXT | Required; `generated`, `accepted`, or `rejected` |
| `selection_filter_json` | TEXT | Required frozen JSON selection criteria |
| `selected_count` | INTEGER | Required count of analyzed entries |
| `ai_model` | TEXT | Required maintenance model name |
| `prompt_template_version` | TEXT | Required prompt version |
| `prompt_template_hash` | TEXT | Required prompt content hash |
| `current_domain_snapshot_json` | TEXT | Required snapshot of current semantic domains |
| `context_snapshot_json` | TEXT | Required snapshot of reserved context labels |
| `proposal_json` | TEXT | Required proposed domain model, definitions, retired domains, and graph edges |
| `rationale` | TEXT | Optional copied model rationale |
| `created_by` | INTEGER | Optional reference to `users.id` |
| `created_at` | TIMESTAMP | Defaults to current timestamp |
| `reviewed_by` | INTEGER | Optional reference to `users.id` |
| `reviewed_at` | TIMESTAMP | Optional review timestamp |
| `review_note` | TEXT | Optional admin review note |

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
  domains, and source attachments.
- Deleting a source cascades to vocabulary-source attachments. Source rows are
  reusable shared records and are not automatically deleted merely because one
  attachment is removed.
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
