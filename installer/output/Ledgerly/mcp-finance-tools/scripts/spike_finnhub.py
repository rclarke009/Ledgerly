#!/usr/bin/env python3
"""Standalone Finnhub quote check (no FastAPI). Reads mcp-finance-tools/.env for FINNHUB_API_KEY."""

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

FINNHUB_QUOTE = "https://finnhub.io/api/v1/quote"


def main() -> None:
    _root = Path(__file__).resolve().parent.parent
    load_dotenv(_root / ".env")
    key = (os.environ.get("FINNHUB_API_KEY") or "").strip()
    if not key:
        print(
            "Set FINNHUB_API_KEY in .env (copy from .env.example) or in the environment.",
            file=sys.stderr,
        )
        sys.exit(1)
    symbol = (sys.argv[1] if len(sys.argv) > 1 else "AAPL").strip().upper()
    if not symbol:
        print("Usage: python spike_finnhub.py [SYMBOL]", file=sys.stderr)
        sys.exit(1)
    r = requests.get(
        FINNHUB_QUOTE,
        params={"symbol": symbol, "token": key},
        timeout=15,
    )
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))


if __name__ == "__main__":
    main()
