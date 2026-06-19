## Config and environment

# Small config module that reads from the environment: things like database path, 
# embedding model name and (if you use a remote API) base URL and API key. 
# Use sensible defaults where safe (e.g. a local SQLite path); never default secrets. 
# Keep config in one place so the rest of the app doesn’t touch `os.environ` directly.

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # Load .env into os.environ; no-op override if Docker already set vars

# Database: SQLite (local) or Postgres (Supabase)
# - For SQLite: set DATABASE_PATH (default ledgerly.db). Leave DATABASE_URL unset/empty.
# - For Postgres/Supabase: set DATABASE_URL to the Postgres connection string from
#   Project Settings → Database → "Connection string" (choose URI). It looks like:
#   postgresql://postgres.[ref]:[PASSWORD]@aws-0-[region].pooler.supabase.com:6543/postgres
#   (This is not the project URL https://xxx.supabase.co — that's for the JS client.)
#   Use pooler port 6543 for short-lived connections; use with psycopg2 or asyncpg.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()  # No default; empty = use SQLite

# SQLite path (used only when DATABASE_URL is empty)
DB_PATH = os.getenv("DATABASE_PATH", "ledgerly.db")

EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
# EMBED_API_KEY = "" # optional for local Ollama; don’t default it. The client should only require it when you’re not using local (e.g. only require it when base URL is not localhost, or allow empty for local).
EMBED_TIMEOUT = int(os.getenv("EMBED_TIMEOUT", 120))
EMBED_MAX_ATTEMPTS = int(os.getenv("EMBED_MAX_ATTEMPTS", 3))
# Max strings per POST /api/embed to Ollama; smaller batches = shorter requests (large PDFs). 0 = single request (legacy).
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "32"))
# Vector dimension for EMBED_MODEL (nomic-embed-text = 768).
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
# Pause after each embed batch (seconds); spreads CPU load. 0 = no pause.
EMBED_INTER_BATCH_SLEEP_SEC = float(os.getenv("EMBED_INTER_BATCH_SLEEP_SEC", "0"))
# SQLite retrieval: max embedding rows scored in Python (0 = no cap). Postgres uses pgvector.
SQLITE_RETRIEVAL_MAX_EMBEDDINGS = int(os.getenv("SQLITE_RETRIEVAL_MAX_EMBEDDINGS", "5000"))
# Background ingest queue: pause between jobs (seconds).
INGEST_QUEUE_INTER_JOB_SLEEP_SEC = float(os.getenv("INGEST_QUEUE_INTER_JOB_SLEEP_SEC", "3"))
# UI hint only: suggested poll interval for job status (seconds).
INGEST_UI_POLL_INTERVAL_SEC = int(os.getenv("INGEST_UI_POLL_INTERVAL_SEC", "60"))

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434")


def _portable_profile() -> str:
    return os.getenv("LEDGERLY_PROFILE", "").strip().lower()


def _resolve_llm_model() -> str:
    raw = os.environ.get("LLM_MODEL")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    if _portable_profile() in ("portable", "low_spec"):
        return "qwen2.5:3b"
    return "qwen3:8b"


LLM_MODEL = _resolve_llm_model()


def _resolve_llava_model() -> str:
    raw = os.environ.get("LLAVA_MODEL")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    if _portable_profile() in ("portable", "low_spec"):
        # Lightweight vision model; `ollama pull moondream` (see setup_and_testing.md).
        return "moondream"
    return "llava:7b"


LLAVA_MODEL = _resolve_llava_model()
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", 60))
LLM_MAX_ATTEMPTS = int(os.getenv("LLM_MAX_ATTEMPTS", 3))
LLM_TOKEN_LIMIT = int(os.getenv("LLM_TOKEN_LIMIT", 10))
LLM_RATE_LIMIT_SECONDS = int(os.getenv("LLM_RATE_LIMIT_SECONDS", 60))
# Pause before each prep LLM call in the ask graph (classifier, finance intent). Spreads CPU load. 0 = no pause.
_default_inter_call_sleep = "2" if _portable_profile() in ("portable", "low_spec") else "0"
LLM_INTER_CALL_SLEEP_SEC = float(os.getenv("LLM_INTER_CALL_SLEEP_SEC", _default_inter_call_sleep))
LLM_STREAM_TIMEOUT_SECONDS = int(os.getenv("LLM_STREAM_TIMEOUT_SECONDS", "600"))
# Max concurrent Ollama HTTP operations (embed + chat + vision). 1 keeps laptops cool.
_default_ollama_concurrent = "1" if _portable_profile() in ("portable", "low_spec") else "2"
OLLAMA_MAX_CONCURRENT = int(os.getenv("OLLAMA_MAX_CONCURRENT", _default_ollama_concurrent))
# Tab-triggered Ollama preload (Ask / Ingest UI). Loads embed + LLM/vision in background.
OLLAMA_WARMUP_ENABLED = os.getenv("OLLAMA_WARMUP_ENABLED", "true").strip().lower() in (
    "true",
    "1",
    "yes",
)
OLLAMA_WARMUP_KEEP_ALIVE = os.getenv("OLLAMA_WARMUP_KEEP_ALIVE", "15m").strip()
OLLAMA_WARMUP_SESSION_SEC = int(os.getenv("OLLAMA_WARMUP_SESSION_SEC", "900"))
# Short pause after ask graph build before streaming final answer.
ASK_COOLDOWN_AFTER_PREP_SEC = float(os.getenv("ASK_COOLDOWN_AFTER_PREP_SEC", "0"))
# Ask local tools (SoT, benchmarks, calcs — no external APIs).
ASK_TOOLS_ENABLED = os.getenv("ASK_TOOLS_ENABLED", "true").strip().lower() in ("true", "1", "yes")
ASK_TOOLS_MAX_PER_QUESTION = int(os.getenv("ASK_TOOLS_MAX_PER_QUESTION", "6"))
# Background ask queue pacing.
ASK_QUEUE_INTER_JOB_SLEEP_SEC = float(os.getenv("ASK_QUEUE_INTER_JOB_SLEEP_SEC", "5"))
ASK_QUEUE_ESTIMATED_WAIT_SEC = int(os.getenv("ASK_QUEUE_ESTIMATED_WAIT_SEC", "600"))

# OpenAI (general-path only: CD advice, rate summary; no PII in prompts).
# Safety: OpenAI is called only with server-built prompts (numbers, product types, fixed text).
# Never send user/institution names, doc content, or raw user questions. Required only when
# using GET /decision OpenAI advice or POST /ask/general.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_TIMEOUT_SECONDS = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "60"))
OPENAI_MAX_ATTEMPTS = int(os.getenv("OPENAI_MAX_ATTEMPTS", "3"))

# Google Drive (read-only ingest). No defaults for secrets.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "")
# Callback URL for one-time OAuth (must match value in Google Cloud Console).
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

# Remote log (Option B: Supabase Edge Function). When set, ERROR/WARNING are POSTed (no PII).
REMOTE_LOG_URL = os.getenv("REMOTE_LOG_URL", "").strip()
REMOTE_LOG_SECRET = os.getenv("REMOTE_LOG_SECRET", "").strip()
REMOTE_LOG_INSTANCE_ID = os.getenv("REMOTE_LOG_INSTANCE_ID", "").strip()
# Supabase anon key: sent as Authorization Bearer when calling Edge Functions (avoids 401 at gateway).
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()

# Re-ranker (two-stage retrieval). When enabled, first stage retrieves initial_k candidates,
# then a local cross-encoder re-ranks them and we keep the top top_k for context.
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "false").strip().lower() in ("true", "1", "yes")
RERANK_INITIAL_K_MULTIPLIER = int(os.getenv("RERANK_INITIAL_K_MULTIPLIER", "3"))
RERANK_INITIAL_K_MAX = int(os.getenv("RERANK_INITIAL_K_MAX", "50"))
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2").strip()

# PDF ingest: image-like / scanned PDFs (native extract + OCR + vision fallback). See setup_and_testing.md.
PDF_WEAK_TEXT_MAX_CHARS_PER_PAGE = int(os.getenv("PDF_WEAK_TEXT_MAX_CHARS_PER_PAGE", "40"))
PDF_VISION_MAX_PAGES = int(os.getenv("PDF_VISION_MAX_PAGES", "20"))
# Above this page count, auto mode uses OCR only for weak text (no vision fallback).
PDF_VISION_PAGE_THRESHOLD = int(os.getenv("PDF_VISION_PAGE_THRESHOLD", "8"))
PDF_OCR_ENABLED = os.getenv("PDF_OCR_ENABLED", "true").strip().lower() in ("true", "1", "yes")
PDF_OCR_MIN_CHARS = int(os.getenv("PDF_OCR_MIN_CHARS", "10"))

# Prometheus HTTP metrics at GET /metrics (default off). Enable when using the observability Compose profile.
METRICS_ENABLED = os.getenv("METRICS_ENABLED", "false").strip().lower() in ("true", "1", "yes")
# One JSON object per line for ask_trace events (easier Loki/Grafana parsing). Other log lines stay human-readable.
LOG_JSON = os.getenv("LOG_JSON", "false").strip().lower() in ("true", "1", "yes")

# Finance MCP (compound interest, stock quotes via Finnhub). Empty = disabled.
# In Docker Compose, set to http://finance-mcp:8000 on the ledgerly service.
FINANCE_TOOLS_BASE_URL = os.getenv("FINANCE_TOOLS_BASE_URL", "").strip().rstrip("/")
FINANCE_TOOLS_TIMEOUT_SECONDS = float(os.getenv("FINANCE_TOOLS_TIMEOUT_SECONDS", "20"))

# Allow POST /documents/{id}/reveal-source when the client is not loopback (default: false).
ALLOW_LOCAL_FILE_REVEAL = os.getenv("ALLOW_LOCAL_FILE_REVEAL", "false").strip().lower() in ("true", "1", "yes")
# Allow PUT /vault/settings from non-loopback (risky on shared servers).
ALLOW_REMOTE_VAULT_SETTINGS = os.getenv("ALLOW_REMOTE_VAULT_SETTINGS", "false").strip().lower() in (
    "true",
    "1",
    "yes",
)

# Learning UI: extract bullet "facts learned" per document via local LLM during ingest.
INGEST_FACTS_ENABLED = os.getenv("INGEST_FACTS_ENABLED", "false").strip().lower() in ("true", "1", "yes")
INGEST_STRUCTURED_ENABLED = os.getenv("INGEST_STRUCTURED_ENABLED", "true").strip().lower() in ("true", "1", "yes")
INGEST_AUTO_TRACK_ENABLED = os.getenv("INGEST_AUTO_TRACK_ENABLED", "true").strip().lower() in ("true", "1", "yes")
RECENT_TRACK_DAYS = int(os.getenv("RECENT_TRACK_DAYS", "7"))
RECENT_TRACK_LIMIT = int(os.getenv("RECENT_TRACK_LIMIT", "10"))
# Only the start of the document is sent; v1 does not multi-pass long PDFs.
INGEST_FACTS_MAX_CHARS = int(os.getenv("INGEST_FACTS_MAX_CHARS", "14000"))
INGEST_STRUCTURED_MAX_CHARS = int(os.getenv("INGEST_STRUCTURED_MAX_CHARS", str(INGEST_FACTS_MAX_CHARS)))

# Decision triggers: flag maturities/obligations within this many days (default 30; 60–90 for earlier reminders).
MATURITY_DAYS_AHEAD = int(os.getenv("MATURITY_DAYS_AHEAD", "30"))
OBLIGATION_DAYS_AHEAD = int(os.getenv("OBLIGATION_DAYS_AHEAD", "30"))
# Cross-check maturing principal vs obligations due within ±N days of maturity.
LIQUIDITY_CROSSCHECK_DAYS = int(os.getenv("LIQUIDITY_CROSSCHECK_DAYS", "14"))
# Curated CD benchmark JSON for rate comparison when no live feed is configured.
REFERENCE_CD_RATES = os.getenv("REFERENCE_CD_RATES", "").strip()
REFERENCE_MMF_APR = float(os.getenv("REFERENCE_MMF_APR", "4.50"))
# IRA / RMD awareness trigger window (days ahead).
IRA_DAYS_AHEAD = int(os.getenv("IRA_DAYS_AHEAD", "45"))

# Optional vault: persistent copies of originals under this absolute directory (host path).
LEDGERLY_ORIGINALS_VAULT = os.getenv("LEDGERLY_ORIGINALS_VAULT", "").strip()
# off | watch_auto | watch_review
_RAW_VAULT_MODE = os.getenv("VAULT_INCOMING_MODE", "off").strip().lower()
VAULT_INCOMING_MODE = _RAW_VAULT_MODE if _RAW_VAULT_MODE in ("off", "watch_auto", "watch_review") else "off"
VAULT_DEBOUNCE_SEC = float(os.getenv("VAULT_DEBOUNCE_SEC", "2"))
# When vault is configured, POST /ingest (text) also writes a UTF-8 .txt snapshot alongside binaries.
VAULT_SAVE_TEXT_INGEST = os.getenv("VAULT_SAVE_TEXT_INGEST", "true").strip().lower() in ("true", "1", "yes")
# When true, ingest fails if the vault exists but copying the original raises (default: warn and continue).
VAULT_INGEST_REQUIRE_WRITE = os.getenv("VAULT_INGEST_REQUIRE_WRITE", "false").strip().lower() in (
    "true",
    "1",
    "yes",
)
# When > 0, skip a second watch_auto/review action for the same incoming relative path within this many seconds (coalesce bursts).
VAULT_PATH_COOLDOWN_SEC = float(os.getenv("VAULT_PATH_COOLDOWN_SEC", "0"))

# old settings if we want to switch to chatgpt:
# so the full embedding URL used by the client becomes http://localhost:11434/api/embeddings (base + path in code).
# EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "https://api.openai.com/v1").rstrip("/")
# EMBED_API_KEY = os.getenv("EMBED_API_KEY", "")
# EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
# EMBED_TIMEOUT = float(os.getenv("EMBED_TIMEOUT", "30"))
# EMBED_MAX_ATTEMPTS = int(os.getenv("EMBED_MAX_ATTEMPTS", "3"))
