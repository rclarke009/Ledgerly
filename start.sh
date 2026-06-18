#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "Starting Ledgerly (Postgres+pgvector internal, Ollama, app, finance MCP)..."
docker compose up -d
echo "Finance MCP (optional, e.g. Cursor): http://localhost:8001/mcp — set FINNHUB_API_KEY in .env for live quotes."

echo "Waiting for Ollama to be ready..."
until docker compose exec -T ollama ollama list >/dev/null 2>&1; do
  sleep 2
done

echo "Making sure models are available (one-time download if needed)..."
if grep -qE '^(LEDGERLY_PROFILE|FINELLY_PROFILE)=(portable|low_spec)' .env 2>/dev/null; then
  docker compose exec -T ollama ollama pull qwen2.5:3b
  docker compose exec -T ollama ollama pull moondream
else
  docker compose exec -T ollama ollama pull qwen3:8b
  docker compose exec -T ollama ollama pull llava:7b
fi
docker compose exec -T ollama ollama pull nomic-embed-text

echo "Waiting for Ledgerly web app..."
until curl -sf http://localhost:8000/health 2>/dev/null | grep -q '"healthy":true'; do
  sleep 2
done

echo ""
echo "Ready. Open in your browser: http://localhost:8000/"
if [ "$(uname -s)" = "Darwin" ]; then
  open "http://localhost:8000/"
fi
echo "To stop later: docker compose down"
