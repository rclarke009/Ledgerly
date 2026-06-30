-- Copy of originals path under LEDGERLY_ORIGINALS_VAULT (vault-relative, POSIX-style).
ALTER TABLE documents ADD COLUMN IF NOT EXISTS original_vault_path TEXT;
