-- Obligation extraction on documents, resolved_at for positions/obligations
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extracted_obligation TEXT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS resolved_at BIGINT;
ALTER TABLE obligations ADD COLUMN IF NOT EXISTS resolved_at BIGINT;
