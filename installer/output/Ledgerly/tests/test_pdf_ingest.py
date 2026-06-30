"""Tests for PDF text extraction modes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.pdf_ingest import PdfTextMode, _native_is_weak, parse_pdf_text_mode, resolve_pdf_for_ingest


def test_parse_pdf_text_mode():
    assert parse_pdf_text_mode("ocr") == PdfTextMode.OCR
    assert parse_pdf_text_mode(None) == PdfTextMode.AUTO
    with pytest.raises(ValueError):
        parse_pdf_text_mode("invalid")


def test_native_is_weak_short_pages():
    assert _native_is_weak([""]) is True
    assert _native_is_weak(["x" * 5]) is True
    assert _native_is_weak(["x" * 100]) is False


@pytest.mark.asyncio
async def test_auto_uses_native_when_strong():
    raw = b"%PDF-1.4 fake"
    with patch("app.pdf_ingest._extract_native_per_page", return_value=["good text " * 20]):
        with patch("app.pdf_ingest._extract_ocr") as mock_ocr:
            text = await resolve_pdf_for_ingest(raw, PdfTextMode.AUTO)
            mock_ocr.assert_not_called()
    assert "good text" in text


@pytest.mark.asyncio
async def test_auto_falls_back_to_ocr_when_weak():
    raw = b"%PDF-1.4 fake"
    with patch("app.pdf_ingest._extract_native_per_page", return_value=[""]):
        with patch("app.pdf_ingest._extract_ocr", return_value="ocr extracted text"):
            with patch("app.pdf_ingest._extract_vision", new_callable=AsyncMock) as mock_vis:
                text = await resolve_pdf_for_ingest(raw, PdfTextMode.AUTO)
                mock_vis.assert_not_called()
    assert text == "ocr extracted text"
