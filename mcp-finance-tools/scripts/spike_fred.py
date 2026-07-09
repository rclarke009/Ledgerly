#!/usr/bin/env python3
"""Standalone FRED Treasury observation check (no FastAPI). Reads mcp-finance-tools/.env for FRED_API_KEY."""

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

FRED_OBSERVATIONS = "https://api.stlouisfed.org/fred/series/observations"


def main() -> None:
    _root = Path(__file__).resolve().parent.parent
    load_dotenv(_root / ".env")
    key = (os.environ.get("FRED_API_KEY") or "").strip()
    if not key:
        print(
            "Set FRED_API_KEY in .env (copy from .env.example) or in the environment.",
            file=sys.stderr,
        )
        sys.exit(1)
    series_id = (sys.argv[1] if len(sys.argv) > 1 else "DGS1").strip().upper()
    if not series_id:
        print("Usage: python spike_fred.py [SERIES_ID]", file=sys.stderr)
        sys.exit(1)
    r = requests.get(
        FRED_OBSERVATIONS,
        params={
            "series_id": series_id,
            "api_key": key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 5,
        },
        timeout=15,
    )
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))


if __name__ == "__main__":
    main()
