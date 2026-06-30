"""Tests for structured position/obligation extraction during ingest."""

import pytest

from app import ingest_structured as structured


SAMPLE_CD_LETTER = """
First National Bank
123 Main Street
Anytown, ST 12345

Certificate of Deposit — Maturity Notice

Account number: ****4521
Date of letter: June 1, 2026

Dear Valued Customer,

This is to inform you that your Certificate of Deposit with First National Bank
will mature on September 15, 2026.

Account summary
Principal: $10,000.00
Annual percentage yield (APR): 4.50%
Maturity date | September 15, 2026

Sincerely,
First National Bank
Deposit Services
"""

SAMPLE_BILL = """
Property Tax Invoice
County Tax Collector

Amount due: $2,500.00
Due date: October 1, 2026

Please pay by the due date to avoid penalties.
"""


def test_parse_json_object_strips_fences():
    raw = 'Here is the data:\n```json\n{"maturity_date": "2026-09-15", "asset_type": "CD"}\n```'
    data = structured.parse_json_object(raw)
    assert data is not None
    assert data["maturity_date"] == "2026-09-15"


def test_normalize_date_month_name():
    assert structured.normalize_date("March 30, 2026") == "2026-03-30"
    assert structured.normalize_date("September 15, 2026") == "2026-09-15"
    assert structured.normalize_date("2026-09-15") == "2026-09-15"
    assert structured.normalize_date("03/30/2026") == "2026-03-30"


def test_regex_extract_position_sample_cd():
    result = structured.regex_extract_position(SAMPLE_CD_LETTER, title="position1.pdf")
    assert result is not None
    assert result["maturity_date"] == "2026-09-15"
    assert result["asset_type"] == "CD"
    assert result["principal"] == 10000.0
    assert result["rate_apr"] == 4.5
    assert "First National Bank" in (result.get("institution") or "")


def test_regex_extract_obligation_sample_bill():
    result = structured.regex_extract_obligation(SAMPLE_BILL, title="property-tax")
    assert result is not None
    assert result["due_date"] == "2026-10-01"
    assert result["amount_estimate"] == 2500.0


@pytest.mark.asyncio
async def test_extract_structured_position_uses_llm_when_regex_misses(monkeypatch):
    async def fake_llm(prompt):
        return (
            '{"institution": "Test Bank", "asset_type": "CD", '
            '"principal": 5000, "rate_apr": 3.25, '
            '"maturity_date": "2027-01-15", "confidence": "high"}'
        )

    monkeypatch.setattr(structured, "regex_extract_position", lambda t, ti=None: None)
    monkeypatch.setattr("app.llm_client.answer_with_context", fake_llm)

    result = await structured.extract_structured_position("Some generic text without dates.")
    assert result is not None
    assert result["maturity_date"] == "2027-01-15"
    assert result["institution"] == "Test Bank"


@pytest.mark.asyncio
async def test_extract_structured_position_regex_fast_path(monkeypatch):
    async def fail_llm(prompt):
        raise AssertionError("LLM should not be called when regex succeeds")

    monkeypatch.setattr("app.llm_client.answer_with_context", fail_llm)

    result = await structured.extract_structured_position(SAMPLE_CD_LETTER, title="position1.pdf")
    assert result is not None
    assert result["maturity_date"] == "2026-09-15"


@pytest.mark.asyncio
async def test_extract_structured_obligation_uses_llm(monkeypatch):
    async def fake_llm(prompt):
        return (
            '{"description": "Car insurance", "due_date": "2026-08-01", '
            '"amount_estimate": 450, "confidence": "high"}'
        )

    monkeypatch.setattr(structured, "regex_extract_obligation", lambda t, ti=None: None)
    monkeypatch.setattr("app.llm_client.answer_with_context", fake_llm)

    result = await structured.extract_structured_obligation("Insurance renewal notice.")
    assert result is not None
    assert result["due_date"] == "2026-08-01"
    assert result["description"] == "Car insurance"
