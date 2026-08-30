"""JPG/PNG ingest: Tesseract first; vision only off portable/low_spec."""

from __future__ import annotations

import base64
import io
import logging

from app.config import PDF_OCR_ENABLED, PDF_OCR_MIN_CHARS, _portable_profile

logger = logging.getLogger(__name__)

PORTABLE_WEAK_OCR_MESSAGE = (
    "You are on the portable profile, so the vision model was skipped to keep this machine cool.\n"
    "OCR could not read enough text (image may be blurry, tiny, or mostly non-text).\n"
    "\n"
    "Options:\n"
    "1. Paste the visible text into Ingest (no image).\n"
    "2. Retake a sharper screenshot and crop to the numbers and labels.\n"
    "3. Leave portable if you accept more heat: comment out LEDGERLY_PROFILE in .env, restart, and retry so vision can run."
)


def _is_cool_profile() -> bool:
    return _portable_profile() in ("portable", "low_spec")


def _ocr_image_bytes(raw: bytes) -> str:
    import pytesseract
    from PIL import Image

    img = Image.open(io.BytesIO(raw))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return (pytesseract.image_to_string(img) or "").strip()


async def extract_image_bytes_for_ingest(
    raw: bytes, *, filename_hint: str | None = None
) -> str:
    ocr_text = ""
    if PDF_OCR_ENABLED:
        try:
            ocr_text = _ocr_image_bytes(raw)
        except Exception as e:
            logger.warning("Image OCR failed: %s", e)

    if ocr_text and len(ocr_text) >= PDF_OCR_MIN_CHARS:
        return ocr_text

    if _is_cool_profile():
        raise ValueError(PORTABLE_WEAK_OCR_MESSAGE)

    from app import llm_client

    image_base64 = base64.b64encode(raw).decode("ascii")
    vision = await llm_client.image_to_text_for_ingest(
        image_base64, filename_hint=filename_hint
    )
    return (vision or "").strip() or ocr_text
