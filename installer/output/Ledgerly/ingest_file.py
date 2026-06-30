#!/usr/bin/env python3
"""
POST a plain-text file to the /ingest endpoint.
Reads the file as-is, builds JSON with text/doc_id/title/source, and sends it.

Activate the project venv first so httpx is available, e.g.:
  source .venv/bin/activate

Usage:
  python ingest_file.py payload.json
  python ingest_file.py doc.txt --doc-id my-doc --title "My Doc"
  # Source defaults to the file's absolute path; override with --source if needed.

Image ingestion (JPG/PNG, e.g. bank screenshots): use POST /ingest/image with
multipart form, e.g. curl -X POST http://localhost:8000/ingest/image -F "file=@screenshot.jpg"
See setup_and_testing.md for details.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a plain-text file via POST /ingest")
    parser.add_argument("file", type=Path, help="Path to plain-text file")
    parser.add_argument("--doc-id", default=None, help="doc_id (default: stem of filename)")
    parser.add_argument("--title", default=None, help="Document title (default: stem of filename)")
    parser.add_argument(
        "--source",
        default=None,
        help="Source label (default: absolute path of the file)",
    )
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the API")
    args = parser.parse_args()

    path = args.file
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    doc_id = args.doc_id if args.doc_id is not None else path.stem
    title = args.title if args.title is not None else path.stem
    source = args.source if args.source is not None else str(path.resolve())

    payload = {
        "text": text,
        "doc_id": doc_id,
        "title": title,
        "source": source,
    }
    body = json.dumps(payload)

    ingest_url = f"{args.url.rstrip('/')}/ingest"
    try:
        response = httpx.post(
            ingest_url,
            content=body,
            headers={"Content-Type": "application/json"},
            timeout=60.0,
        )
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))
    except httpx.HTTPStatusError as e:
        print(f"HTTP {e.response.status_code}: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except httpx.RequestError as e:
        print(f"Request failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
