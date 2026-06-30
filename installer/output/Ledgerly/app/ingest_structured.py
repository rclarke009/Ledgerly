"""Structured extraction during ingest (optional)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from app.config import INGEST_STRUCTURED_MAX_CHARS
from app.models import ExtractedObligation, ExtractedPosition

logger = logging.getLogger(__name__)

_MONTH_NAMES = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_MONTH_ABBR = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")

_DATE_PATTERNS = (
    re.compile(
        r"\b(" + "|".join(_MONTH_NAMES) + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(" + "|".join(_MONTH_ABBR) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),
)

_POSITION_DATE_LABELS = re.compile(
    r"(?:maturity\s*date|matures?\s+on|term\s+end|mature\s+on)\s*[:\-]?\s*",
    re.IGNORECASE,
)
_OBLIGATION_DATE_LABELS = re.compile(
    r"(?:due\s+date|payment\s+due|pay\s+by|due\s+on|due\s+by)\s*[:\-]?\s*",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)")
_RATE_RE = re.compile(
    r"(?:apr|annual\s+percentage\s+yield|interest\s+rate|rate)(?:\s*\([^)]*\))?\s*[:\-]?\s*([\d.]+)\s*%?",
    re.IGNORECASE,
)
_INSTITUTION_RE = re.compile(
    r"^([A-Z][A-Za-z0-9&\-\s]{2,60}(?:Bank|Credit Union|FCU|CU))\b",
    re.MULTILINE,
)


def detect_tax_document_tags(text: str, title: str | None = None) -> list[str]:
    tags: list[str] = []
    blob = f"{title or ''} {text or ''}".lower()
    if "1099" in blob:
        tags.append("1099")
    if "w-2" in blob or "w2" in blob:
        tags.append("w2")
    return tags


def normalize_date(value: str | None) -> str | None:
    """Convert common date strings to YYYY-MM-DD."""
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw[:10]):
        return raw[:10]
    for fmt in ("%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.replace("  ", " "), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    for pat in _DATE_PATTERNS[:2]:
        m = pat.search(raw)
        if not m:
            continue
        month_str, day_str, year_str = m.group(1), m.group(2), m.group(3)
        month_str = month_str.lower().rstrip(".")
        for i, name in enumerate(_MONTH_NAMES):
            if month_str == name or (i < len(_MONTH_ABBR) and month_str == _MONTH_ABBR[i]):
                try:
                    return datetime(int(year_str), i + 1, int(day_str)).strftime("%Y-%m-%d")
                except ValueError:
                    return None
    m = _DATE_PATTERNS[2].search(raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = _DATE_PATTERNS[3].search(raw)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2))).strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def parse_json_object(raw: str) -> dict[str, Any] | None:
    """Extract a JSON object from an LLM response."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _find_labeled_date(text: str, label_re: re.Pattern[str]) -> str | None:
    for m in label_re.finditer(text):
        snippet = text[m.end() : m.end() + 80]
        for pat in _DATE_PATTERNS:
            dm = pat.search(snippet)
            if dm:
                normalized = normalize_date(dm.group(0))
                if normalized:
                    return normalized
    return None


def _parse_money(text: str) -> float | None:
    m = _MONEY_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_rate(text: str) -> float | None:
    m = _RATE_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _parse_institution(text: str) -> str | None:
    m = _INSTITUTION_RE.search(text)
    if m:
        return m.group(1).strip()
    return None


def _position_dict_from_model(model: ExtractedPosition) -> dict[str, Any]:
    return model.model_dump(exclude_none=False)


def _obligation_dict_from_model(model: ExtractedObligation) -> dict[str, Any]:
    return model.model_dump(exclude_none=False)


def regex_extract_position(text: str, title: str | None = None) -> dict[str, Any] | None:
    """Fast-path extraction for obvious CD maturity letters."""
    blob = f"{title or ''}\n{text or ''}"
    if not re.search(r"\b(certificate of deposit|\bcd\b|maturity)\b", blob, re.IGNORECASE):
        maturity = _find_labeled_date(blob, _POSITION_DATE_LABELS)
        if not maturity:
            return None
    else:
        maturity = _find_labeled_date(blob, _POSITION_DATE_LABELS)
        if not maturity:
            for pat in _DATE_PATTERNS:
                dm = pat.search(blob)
                if dm:
                    maturity = normalize_date(dm.group(0))
                    if maturity:
                        break
    if not maturity:
        return None
    institution = _parse_institution(blob)
    principal = _parse_money(blob)
    rate_apr = _parse_rate(blob)
    asset_type = "CD"
    if re.search(r"\bmoney market\b", blob, re.IGNORECASE):
        asset_type = "Money market"
    elif re.search(r"\btreasury\b", blob, re.IGNORECASE):
        asset_type = "Treasury"
    return _position_dict_from_model(
        ExtractedPosition(
            institution=institution,
            asset_type=asset_type,
            principal=principal,
            rate_apr=rate_apr,
            maturity_date=maturity,
            confidence="medium",
        )
    )


def regex_extract_obligation(text: str, title: str | None = None) -> dict[str, Any] | None:
    """Fast-path extraction for obvious bills with due dates."""
    blob = f"{title or ''}\n{text or ''}"
    due_date = _find_labeled_date(blob, _OBLIGATION_DATE_LABELS)
    if not due_date:
        if not re.search(r"\b(bill|invoice|payment due|amount due|premium)\b", blob, re.IGNORECASE):
            return None
        for pat in _DATE_PATTERNS:
            dm = pat.search(blob)
            if dm:
                due_date = normalize_date(dm.group(0))
                if due_date:
                    break
    if not due_date:
        return None
    description = (title or "").strip() or "Bill"
    amount = _parse_money(blob)
    return _obligation_dict_from_model(
        ExtractedObligation(
            description=description,
            due_date=due_date,
            amount_estimate=amount,
            confidence="medium",
        )
    )


def _truncate_for_prompt(text: str, title: str | None) -> str:
    parts: list[str] = []
    if title and title.strip():
        parts.append(f"Title: {title.strip()}")
    parts.append(text or "")
    combined = "\n\n".join(parts)
    if len(combined) <= INGEST_STRUCTURED_MAX_CHARS:
        return combined
    return combined[:INGEST_STRUCTURED_MAX_CHARS]


def _position_prompt(document: str) -> str:
    return (
        "Extract financial position details from this document. "
        "Look for CDs, money market accounts, treasuries, or similar holdings with a maturity date.\n\n"
        f"{document}\n\n"
        "Return ONLY a JSON object with these keys (use null when unknown):\n"
        "institution, asset_type, description, principal, rate_apr, maturity_date, confidence\n"
        "- asset_type: e.g. CD, Money market, Treasury\n"
        "- principal: number without $ or commas\n"
        "- rate_apr: number (e.g. 4.5 for 4.5%)\n"
        "- maturity_date: YYYY-MM-DD\n"
        "- confidence: high, medium, or low\n"
        "If there is no maturity date, return {\"maturity_date\": null}."
    )


def _obligation_prompt(document: str) -> str:
    return (
        "Extract bill or obligation details from this document.\n\n"
        f"{document}\n\n"
        "Return ONLY a JSON object with these keys (use null when unknown):\n"
        "description, due_date, amount_estimate, priority, confidence\n"
        "- description: short label for the bill\n"
        "- due_date: YYYY-MM-DD\n"
        "- amount_estimate: number without $ or commas\n"
        "- confidence: high, medium, or low\n"
        "If there is no due date, return {\"due_date\": null}."
    )


def _normalize_position_dict(data: dict[str, Any]) -> dict[str, Any] | None:
    maturity = normalize_date(data.get("maturity_date"))
    if not maturity:
        return None
    data["maturity_date"] = maturity
    for key in ("principal", "rate_apr"):
        val = data.get(key)
        if val is not None and not isinstance(val, (int, float)):
            try:
                data[key] = float(str(val).replace(",", "").replace("$", "").replace("%", ""))
            except ValueError:
                data[key] = None
    try:
        model = ExtractedPosition(**data)
    except Exception:
        return None
    return _position_dict_from_model(model)


def _normalize_obligation_dict(data: dict[str, Any]) -> dict[str, Any] | None:
    due = normalize_date(data.get("due_date"))
    if not due:
        return None
    data["due_date"] = due
    val = data.get("amount_estimate")
    if val is not None and not isinstance(val, (int, float)):
        try:
            data["amount_estimate"] = float(str(val).replace(",", "").replace("$", ""))
        except ValueError:
            data["amount_estimate"] = None
    if not data.get("description"):
        data["description"] = "Bill"
    try:
        model = ExtractedObligation(**data)
    except Exception:
        return None
    return _obligation_dict_from_model(model)


async def extract_structured_position(text: str, title: str | None = None) -> dict[str, Any] | None:
    try:
        fast = regex_extract_position(text, title)
        if fast and fast.get("maturity_date"):
            return fast
    except Exception as e:
        logger.warning("ingest structured position regex: %s", e)

    try:
        from app import llm_client

        prompt = _position_prompt(_truncate_for_prompt(text, title))
        raw = await llm_client.answer_with_context(prompt)
        data = parse_json_object(raw or "")
        if not data:
            return None
        return _normalize_position_dict(data)
    except Exception as e:
        logger.warning("ingest structured position LLM: %s", e)
        return None


async def extract_structured_obligation(text: str, title: str | None = None) -> dict[str, Any] | None:
    try:
        fast = regex_extract_obligation(text, title)
        if fast and fast.get("due_date"):
            return fast
    except Exception as e:
        logger.warning("ingest structured obligation regex: %s", e)

    try:
        from app import llm_client

        prompt = _obligation_prompt(_truncate_for_prompt(text, title))
        raw = await llm_client.answer_with_context(prompt)
        data = parse_json_object(raw or "")
        if not data:
            return None
        return _normalize_obligation_dict(data)
    except Exception as e:
        logger.warning("ingest structured obligation LLM: %s", e)
        return None
