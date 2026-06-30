#!/usr/bin/env bash
set -e
LEDGERLY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$LEDGERLY_DIR"

if [ -z "${OLLAMA_NUM_THREADS:-}" ]; then
  export OLLAMA_NUM_THREADS="$(python3 -c 'from app.cpu_defaults import default_ollama_num_threads; print(default_ollama_num_threads())')"
  echo "OLLAMA_NUM_THREADS=${OLLAMA_NUM_THREADS} (auto-detected, conservative)"
fi

OLLAMA_ALREADY_RUNNING=false
if curl -s -o /dev/null -w "%{http_code}" http://localhost:11434/api/tags 2>/dev/null | grep -q 200; then
  OLLAMA_ALREADY_RUNNING=true
fi

# Start Ollama in background if not already responding
if [ "$OLLAMA_ALREADY_RUNNING" = false ]; then
  echo "Starting Ollama..."
  ollama serve &
  sleep 2
elif [ -n "${OLLAMA_NUM_THREADS:-}" ]; then
  echo "Note: Ollama is already running; restart it for OLLAMA_NUM_THREADS=${OLLAMA_NUM_THREADS} to take effect."
fi

# Wait for Ollama to be ready (up to 30s), then ensure vision model is available for /ask/image and /ingest/image
echo "Waiting for Ollama..."
for i in $(seq 1 30); do
  if curl -s -o /dev/null -w "%{http_code}" http://localhost:11434/api/tags 2>/dev/null | grep -q 200; then
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "Ollama did not become ready in time. Start it manually (ollama serve) and run this script again."
    exit 1
  fi
  sleep 1
done
echo "Ensuring text LLM (qwen3:8b) is available..."
ollama pull qwen3:8b
echo "Ensuring vision model (llava:7b) is available for image features..."
ollama pull llava:7b

# Prefer .venv, fallback to .venv-mlx
if [ -d ".venv" ]; then
  source .venv/bin/activate
elif [ -d ".venv-mlx" ]; then
  source .venv-mlx/bin/activate
else
  echo "No .venv or .venv-mlx found. Create one and install deps first."
  exit 1
fi

echo "Starting Ledgerly at http://localhost:8000"
# Exclude venv trees — pip installs there trigger endless reload loops with --reload.
exec uvicorn app.main:app --reload \
  --reload-exclude '.venv' \
  --reload-exclude '.venv-mlx'
