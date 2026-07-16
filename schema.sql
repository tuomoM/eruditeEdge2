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
    definition_key TEXT NOT NULL DEFAULT '',
    context TEXT,
    part_of_speech TEXT NOT NULL DEFAULT 'other'
        CHECK (part_of_speech IN ('noun', 'verb', 'adjective', 'adverb', 'phrase', 'other')),
    frequency_band TEXT
        CHECK (
            frequency_band IS NULL OR frequency_band IN (
                'common',
                'uncommon',
                'rare',
                'very_rare',
                'archaic_or_obsolete',
                'specialized'
            )
        ),
    frequency_note TEXT,
    needs_attention TEXT
        CHECK (needs_attention IS NULL OR length(needs_attention) <= 200),
    confidence_score INTEGER
        CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100),
    confidence_obsolete INTEGER NOT NULL DEFAULT 0
        CHECK (confidence_obsolete IN (0, 1)),
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX vocabulary_entries_sense_unique_idx
ON vocabulary_entries(lower(word), part_of_speech, definition_key);

CREATE TABLE vocabulary_synonyms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
    linked_vocabulary_id INTEGER REFERENCES vocabulary_entries(id) ON DELETE SET NULL,
    synonym TEXT NOT NULL,
    UNIQUE (vocabulary_id, synonym)
);

CREATE INDEX vocabulary_synonyms_linked_vocabulary_id_idx
ON vocabulary_synonyms(linked_vocabulary_id);

CREATE INDEX vocabulary_synonyms_synonym_nocase_idx
ON vocabulary_synonyms(synonym COLLATE NOCASE);

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
    domain TEXT NOT NULL,
    domain_order INTEGER NOT NULL CHECK (domain_order BETWEEN 1 AND 4),
    UNIQUE (vocabulary_id, domain),
    UNIQUE (vocabulary_id, domain_order)
);

CREATE TABLE vocabulary_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    author TEXT,
    source_type TEXT NOT NULL DEFAULT 'other',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX vocabulary_sources_name_author_idx
ON vocabulary_sources(name COLLATE NOCASE, author COLLATE NOCASE, source_type);

CREATE TABLE vocabulary_entry_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
    source_id INTEGER NOT NULL REFERENCES vocabulary_sources(id) ON DELETE CASCADE,
    note TEXT NOT NULL DEFAULT '',
    source_order INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (vocabulary_id, source_order)
);

CREATE INDEX vocabulary_entry_sources_vocabulary_id_idx
ON vocabulary_entry_sources(vocabulary_id);

CREATE INDEX vocabulary_entry_sources_source_id_idx
ON vocabulary_entry_sources(source_id);

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

CREATE TABLE background_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'failed')),
    payload TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0
        CHECK (attempts >= 0),
    last_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX background_jobs_status_type_idx
ON background_jobs(status, job_type, created_at);

CREATE TABLE vocabulary_maintenance_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (
            status IN (
                'draft',
                'ready',
                'running',
                'completed',
                'partially_failed',
                'promoted',
                'rolled_back',
                'failed'
            )
        ),
    selection_filter_json TEXT NOT NULL,
    selected_count INTEGER NOT NULL DEFAULT 0 CHECK (selected_count >= 0),
    taxonomy_snapshot_json TEXT NOT NULL,
    frequency_rubric_snapshot_json TEXT NOT NULL,
    prompt_template_version TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    response_schema_version TEXT NOT NULL,
    validator_version TEXT NOT NULL,
    ai_model TEXT NOT NULL,
    max_items INTEGER CHECK (max_items IS NULL OR max_items > 0),
    max_estimated_cost REAL CHECK (max_estimated_cost IS NULL OR max_estimated_cost >= 0),
    estimated_input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (estimated_input_tokens >= 0),
    estimated_output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (estimated_output_tokens >= 0),
    actual_input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (actual_input_tokens >= 0),
    actual_output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (actual_output_tokens >= 0),
    actual_cost REAL NOT NULL DEFAULT 0 CHECK (actual_cost >= 0),
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    promoted_at TIMESTAMP,
    error_summary TEXT
);

CREATE TABLE vocabulary_maintenance_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES vocabulary_maintenance_runs(id) ON DELETE CASCADE,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
    item_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            item_status IN (
                'pending',
                'claimed',
                'generated',
                'validated',
                'accepted',
                'rejected',
                'stale_conflict',
                'promoted',
                'failed'
            )
        ),
    source_snapshot_json TEXT NOT NULL,
    source_snapshot_hash TEXT NOT NULL,
    source_updated_at TIMESTAMP,
    proposed_context TEXT,
    proposed_frequency_band TEXT,
    proposed_frequency_note TEXT,
    proposed_domains_json TEXT,
    proposed_needs_attention TEXT,
    model_confidence INTEGER CHECK (model_confidence IS NULL OR model_confidence BETWEEN 0 AND 100),
    review_priority INTEGER CHECK (review_priority IS NULL OR review_priority BETWEEN 0 AND 100),
    rationale TEXT,
    alternate_domains_json TEXT,
    needs_sense_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_sense_review IN (0, 1)),
    sense_note TEXT,
    raw_response_excerpt TEXT,
    parsed_response_json TEXT,
    validation_errors_json TEXT,
    failure_type TEXT
        CHECK (
            failure_type IS NULL OR failure_type IN (
                'api_transient',
                'api_permanent',
                'invalid_json',
                'validation_failed',
                'conflict',
                'budget_exceeded'
            )
        ),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    claimed_by TEXT,
    claimed_at TIMESTAMP,
    lease_expires_at TIMESTAMP,
    generated_at TIMESTAMP,
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP,
    rejection_note TEXT,
    promoted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, vocabulary_id)
);

CREATE TABLE vocabulary_maintenance_promotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES vocabulary_maintenance_runs(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES vocabulary_maintenance_items(id) ON DELETE CASCADE,
    vocabulary_id INTEGER NOT NULL REFERENCES vocabulary_entries(id) ON DELETE CASCADE,
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    promoted_by INTEGER REFERENCES users(id),
    promoted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    rolled_back_by INTEGER REFERENCES users(id),
    rolled_back_at TIMESTAMP
);

CREATE INDEX vocabulary_maintenance_runs_status_idx
ON vocabulary_maintenance_runs(status, created_at);

CREATE INDEX vocabulary_maintenance_items_run_status_idx
ON vocabulary_maintenance_items(run_id, item_status, id);

CREATE INDEX vocabulary_maintenance_items_vocabulary_idx
ON vocabulary_maintenance_items(vocabulary_id);

CREATE INDEX vocabulary_maintenance_promotions_run_idx
ON vocabulary_maintenance_promotions(run_id, promoted_at);

CREATE TABLE vocabulary_domain_model_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'generated'
        CHECK (status IN ('generated', 'accepted', 'rejected')),
    selection_filter_json TEXT NOT NULL,
    selected_count INTEGER NOT NULL DEFAULT 0 CHECK (selected_count >= 0),
    ai_model TEXT NOT NULL,
    prompt_template_version TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    current_domain_snapshot_json TEXT NOT NULL,
    context_snapshot_json TEXT NOT NULL,
    proposal_json TEXT NOT NULL,
    rationale TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP,
    review_note TEXT
);

CREATE INDEX vocabulary_domain_model_proposals_status_idx
ON vocabulary_domain_model_proposals(status, created_at);

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
