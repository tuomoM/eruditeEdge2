CREATE TABLE IF NOT EXISTS ai_generation_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    generation_date TEXT NOT NULL,
    generation_count INTEGER NOT NULL DEFAULT 0
        CHECK (generation_count >= 0),
    UNIQUE (user_id, generation_date)
);
