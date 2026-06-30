-- Ledgerly: Financial tables (Private Cash Assistant)
-- Run after 20250302000000_phase1_schema.sql
-- Matches app/db.py financial schema.

-- =============================================================================
-- Tables
-- =============================================================================
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT,
    institution TEXT,
    document_id TEXT,
    created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    asset_type TEXT NOT NULL,
    description TEXT,
    principal REAL,
    rate_apr REAL,
    maturity_date TEXT,
    document_id TEXT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS obligations (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    due_date TEXT NOT NULL,
    amount_estimate REAL,
    priority TEXT,
    document_id TEXT,
    created_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS trigger_events (
    id TEXT PRIMARY KEY,
    trigger_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    event_date TEXT,
    evaluated_at BIGINT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_history (
    id TEXT PRIMARY KEY,
    evaluated_at BIGINT NOT NULL,
    status TEXT NOT NULL,
    memo TEXT,
    trigger_ids TEXT
);

CREATE TABLE IF NOT EXISTS rate_snapshots (
    id TEXT PRIMARY KEY,
    fetched_at BIGINT NOT NULL,
    product_type TEXT NOT NULL,
    term_months INTEGER,
    rate_apr REAL,
    source_url TEXT,
    source_name TEXT,
    quote TEXT
);

-- =============================================================================
-- Indexes
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_positions_account_id ON positions(account_id);
CREATE INDEX IF NOT EXISTS idx_positions_maturity ON positions(maturity_date);
CREATE INDEX IF NOT EXISTS idx_obligations_due_date ON obligations(due_date);
CREATE INDEX IF NOT EXISTS idx_trigger_events_evaluated_at ON trigger_events(evaluated_at);
CREATE INDEX IF NOT EXISTS idx_decision_history_evaluated_at ON decision_history(evaluated_at);
