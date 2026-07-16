CREATE TABLE IF NOT EXISTS vocabulary_domain_model_proposals (
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

CREATE INDEX IF NOT EXISTS vocabulary_domain_model_proposals_status_idx
ON vocabulary_domain_model_proposals(status, created_at);
