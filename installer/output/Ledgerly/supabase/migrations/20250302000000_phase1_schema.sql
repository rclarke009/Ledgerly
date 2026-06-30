-- Ledgerly Phase 1: Supabase schema (Postgres + pgvector + RLS)
-- Project: YOUR_PROJECT_REF — https://YOUR_PROJECT_REF.supabase.co
-- Run in Supabase Dashboard → SQL Editor (or: supabase db push)
-- Matches app/db.py with embedding as vector(768) for nomic-embed-text.

-- =============================================================================
-- 1. Extensions
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- 2. Tables
-- =============================================================================
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    title TEXT,
    source TEXT,
    created_at BIGINT
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT,
    start_offset INTEGER,
    end_offset INTEGER
);

CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    model TEXT,
    embedding vector(768),
    dim INTEGER
);

-- =============================================================================
-- 3. Indexes
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id_chunk_index ON chunks(doc_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(model);

-- HNSW index for cosine similarity (retrieval: ORDER BY embedding <=> query_vec)
CREATE INDEX IF NOT EXISTS idx_embeddings_embedding_hnsw
ON embeddings USING hnsw (embedding vector_cosine_ops);

-- =============================================================================
-- 4. Row Level Security (RLS)
-- =============================================================================
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE embeddings ENABLE ROW LEVEL SECURITY;

-- Policies: allow full access for authenticated users (Supabase Auth).
-- Direct Postgres connection (DATABASE_URL) uses the postgres role and bypasses RLS.
-- service_role key also bypasses RLS. anon has no access unless you add a policy.

CREATE POLICY "documents_authenticated_all"
ON documents FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);

CREATE POLICY "chunks_authenticated_all"
ON chunks FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);

CREATE POLICY "embeddings_authenticated_all"
ON embeddings FOR ALL
TO authenticated
USING (true)
WITH CHECK (true);

-- Optional: allow anon read-only for public RAG (uncomment if needed).
-- CREATE POLICY "documents_anon_select" ON documents FOR SELECT TO anon USING (true);
-- CREATE POLICY "chunks_anon_select" ON chunks FOR SELECT TO anon USING (true);
-- CREATE POLICY "embeddings_anon_select" ON embeddings FOR SELECT TO anon USING (true);
