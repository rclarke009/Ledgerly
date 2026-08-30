"""Tests for JPG/PNG ingest OCR vs vision fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.image_ingest import PORTABLE_WEAK_OCR_MESSAGE, extract_image_bytes_for_ingest


@pytest.mark.asyncio
async def test_ocr_strong_skips_vision(monkeypatch):
    monkeypatch.setenv("LEDGERLY_PROFILE", "portable")
    with patch("app.image_ingest._ocr_image_bytes", return_value="payment history principal interest " * 3):
        with patch("app.llm_client.image_to_text_for_ingest", new_callable=AsyncMock) as mock_vis:
            text = await extract_image_bytes_for_ingest(b"\x89PNG fake")
            mock_vis.assert_not_called()
    assert "payment history" in text


@pytest.mark.asyncio
async def test_portable_weak_ocr_raises_options_message(monkeypatch):
    monkeypatch.setenv("LEDGERLY_PROFILE", "portable")
    with patch("app.image_ingest._ocr_image_bytes", return_value="hi"):
        with patch("app.llm_client.image_to_text_for_ingest", new_callable=AsyncMock) as mock_vis:
            with pytest.raises(ValueError) as exc:
                await extract_image_bytes_for_ingest(b"\x89PNG fake")
            mock_vis.assert_not_called()
    msg = str(exc.value)
    assert msg == PORTABLE_WEAK_OCR_MESSAGE
    assert "portable" in msg.lower()
    assert "paste" in msg.lower()
    assert "screenshot" in msg.lower()
    assert "LEDGERLY_PROFILE" in msg
    assert "Leave portable" in msg


@pytest.mark.asyncio
async def test_non_portable_weak_ocr_calls_vision(monkeypatch):
    monkeypatch.setenv("LEDGERLY_PROFILE", "")
    with patch("app.image_ingest._ocr_image_bytes", return_value="hi"):
        with patch(
            "app.llm_client.image_to_text_for_ingest",
            new_callable=AsyncMock,
            return_value="Vision extracted payment $2,308.38",
        ) as mock_vis:
            text = await extract_image_bytes_for_ingest(b"\x89PNG fake", filename_hint="shot.png")
            mock_vis.assert_awaited_once()
    assert "2,308.38" in text
