CREATE TABLE IF NOT EXISTS vocabulary_maintenance_runs (
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

CREATE TABLE IF NOT EXISTS vocabulary_maintenance_items (
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

CREATE TABLE IF NOT EXISTS vocabulary_maintenance_promotions (
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

CREATE INDEX IF NOT EXISTS vocabulary_maintenance_runs_status_idx
ON vocabulary_maintenance_runs(status, created_at);

CREATE INDEX IF NOT EXISTS vocabulary_maintenance_items_run_status_idx
ON vocabulary_maintenance_items(run_id, item_status, id);

CREATE INDEX IF NOT EXISTS vocabulary_maintenance_items_vocabulary_idx
ON vocabulary_maintenance_items(vocabulary_id);

CREATE INDEX IF NOT EXISTS vocabulary_maintenance_promotions_run_idx
ON vocabulary_maintenance_promotions(run_id, promoted_at);
