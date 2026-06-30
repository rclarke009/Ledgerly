"""PDF ingest helpers: native text, OCR, and optional vision fallback."""

from __future__ import annotations

import base64
import io
import logging
from enum import Enum

from app.config import (
    PDF_OCR_ENABLED,
    PDF_OCR_MIN_CHARS,
    PDF_VISION_MAX_PAGES,
    PDF_VISION_PAGE_THRESHOLD,
    PDF_WEAK_TEXT_MAX_CHARS_PER_PAGE,
)

logger = logging.getLogger(__name__)


class PdfTextMode(str, Enum):
    AUTO = "auto"
    NATIVE = "native"
    OCR = "ocr"
    VISION = "vision"


def _extract_native_per_page(raw: bytes) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    return [(page.extract_text() or "").strip() for page in reader.pages]


def _join_pages(pages: list[str]) -> str:
    return "\n\n".join(p for p in pages if p).strip()


def _native_is_weak(pages: list[str]) -> bool:
    if not pages:
        return True
    total = sum(len(p) for p in pages)
    if total < PDF_OCR_MIN_CHARS:
        return True
    for page in pages:
        if len(page) < PDF_WEAK_TEXT_MAX_CHARS_PER_PAGE:
            return True
    return False


def _extract_ocr(raw: bytes) -> str:
    import fitz
    import pytesseract
    from PIL import Image

    doc = fitz.open(stream=raw, filetype="pdf")
    parts: list[str] = []
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=150)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = (pytesseract.image_to_string(img) or "").strip()
            if text:
                parts.append(text)
    finally:
        doc.close()
    return _join_pages(parts)


async def _extract_vision(raw: bytes, max_pages: int) -> str:
    import fitz

    from app import llm_client

    doc = fitz.open(stream=raw, filetype="pdf")
    parts: list[str] = []
    try:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(dpi=150)
            b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
            text = (await llm_client.image_to_text_for_ingest(b64) or "").strip()
            if text:
                parts.append(text)
    finally:
        doc.close()
    return _join_pages(parts)


async def resolve_pdf_for_ingest(raw: bytes, mode: PdfTextMode = PdfTextMode.AUTO) -> str:
    pages = _extract_native_per_page(raw)
    native = _join_pages(pages)
    page_count = max(len(pages), 1)

    if mode == PdfTextMode.NATIVE:
        return native

    if mode == PdfTextMode.OCR:
        if not PDF_OCR_ENABLED:
            raise ValueError("PDF OCR is disabled (PDF_OCR_ENABLED=false).")
        return _extract_ocr(raw) or native

    if mode == PdfTextMode.VISION:
        return await _extract_vision(raw, PDF_VISION_MAX_PAGES) or native

    # AUTO: native when strong enough, else OCR, then vision on small PDFs only.
    if native and not _native_is_weak(pages):
        return native

    ocr_text = ""
    if PDF_OCR_ENABLED:
        try:
            ocr_text = _extract_ocr(raw)
        except Exception as e:
            logger.warning("PDF OCR failed in auto mode: %s", e)

    if ocr_text and len(ocr_text) >= PDF_OCR_MIN_CHARS:
        return ocr_text

    if page_count <= PDF_VISION_PAGE_THRESHOLD:
        try:
            vision_text = await _extract_vision(raw, PDF_VISION_MAX_PAGES)
        except Exception as e:
            logger.warning("PDF vision fallback failed: %s", e)
            vision_text = ""
        if vision_text and len(vision_text) >= PDF_OCR_MIN_CHARS:
            return vision_text

    return ocr_text or native


def parse_pdf_text_mode(value: str | None) -> PdfTextMode:
    if not value:
        return PdfTextMode.AUTO
    try:
        return PdfTextMode(str(value).strip().lower())
    except ValueError:
        raise ValueError(
            f"Invalid pdf_text_mode: {value!r}. Use auto, native, ocr, or vision."
        ) from None
