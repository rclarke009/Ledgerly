-- Pending structured position suggestion from document ingest (confirm on Home).
ALTER TABLE documents ADD COLUMN IF NOT EXISTS extracted_position TEXT;
