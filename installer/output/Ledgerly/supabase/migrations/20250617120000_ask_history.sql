CREATE TABLE IF NOT EXISTS ask_history (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    asked_at BIGINT NOT NULL,
    status TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT,
    tables_json TEXT,
    charts_json TEXT,
    route TEXT,
    doc_filter TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_ask_history_asked_at ON ask_history(asked_at DESC);
