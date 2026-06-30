ALTER TABLE ask_history ADD COLUMN IF NOT EXISTS conversation_id TEXT;
ALTER TABLE ask_history ADD COLUMN IF NOT EXISTS parent_id TEXT;
ALTER TABLE ask_history ADD COLUMN IF NOT EXISTS related_docs_json TEXT;
ALTER TABLE ask_history ADD COLUMN IF NOT EXISTS top_chunks_json TEXT;

CREATE INDEX IF NOT EXISTS idx_ask_history_conversation_id ON ask_history(conversation_id);
