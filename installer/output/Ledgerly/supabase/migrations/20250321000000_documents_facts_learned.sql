-- Optional per-document bullet facts (JSON array of strings) for learning / review UI.

ALTER TABLE documents ADD COLUMN IF NOT EXISTS facts_learned TEXT;
