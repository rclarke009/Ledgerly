-- CD ladder columns, IRA overview table (Ledgerly Version 1 CD assistant)

ALTER TABLE positions ADD COLUMN IF NOT EXISTS start_date TEXT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS next_action TEXT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS liquidity_note TEXT;

CREATE TABLE IF NOT EXISTS ira_overview (
    id TEXT PRIMARY KEY,
    account_name TEXT NOT NULL,
    institution TEXT,
    account_type TEXT,
    balance_estimate REAL,
    rmd_note TEXT,
    next_relevant_date TEXT,
    document_id TEXT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);
