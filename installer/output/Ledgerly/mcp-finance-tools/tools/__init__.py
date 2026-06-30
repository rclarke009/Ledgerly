"""MCP finance tools package."""

from pathlib import Path

from dotenv import load_dotenv

# Load mcp-finance-tools/.env before any tool reads os.environ (e.g. FINNHUB_API_KEY).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
