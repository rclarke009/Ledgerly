#!/usr/bin/env bash
# Build Ledgerly-Portable.zip using only Docker. No Inno Setup required.
# Run from project root or from installer.
# Output: installer/output/Ledgerly-Portable.zip
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$REPO_ROOT/installer/output"
ZIP_NAME="Ledgerly-Portable.zip"
mkdir -p "$OUT_DIR"

# Use Docker (alpine) to build zip: copy app into a clean Ledgerly folder, exclude cruft, zip
docker run --rm \
  -v "$REPO_ROOT:/src:ro" \
  -v "$OUT_DIR:/out" \
  -w /work \
  alpine:latest \
  sh -c '
    apk add --no-cache zip >/dev/null &&
    rm -rf /work && mkdir -p /work/Ledgerly &&
    cd /src &&
    for f in *; do
      case "$f" in
        .env|.git|__pycache__|.venv|installer|.idea|.vscode) ;;
        *) cp -R "$f" /work/Ledgerly/ 2>/dev/null || true ;;
      esac
    done &&
    for dot in .dockerignore .env.example .env.portable-xps15.example; do [ -f /src/$dot ] && cp /src/$dot /work/Ledgerly/; done &&
    find /work/Ledgerly -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true &&
    rm -f /work/Ledgerly/*.sqlite /work/Ledgerly/payload.json 2>/dev/null || true &&
    (cd /work && zip -r /out/'"$ZIP_NAME"' Ledgerly -x "*.DS_Store" "Ledgerly/installer/*" "*__pycache__*" "*.sqlite" "Ledgerly/payload.json")
  '

echo "Built: $OUT_DIR/$ZIP_NAME"
