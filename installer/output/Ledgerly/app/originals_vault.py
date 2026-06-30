"""Originals vault — persist uploaded files for Preview/Open."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

REL_ORIGINALS = "originals"
REL_INCOMING = "incoming"
REL_PENDING = "pending"


def vault_enabled() -> bool:
    return bool(resolve_vault_root())


def resolve_vault_root() -> str | None:
    from app.vault_settings_store import resolve_vault_root as _resolve

    return _resolve()


def vault_watcher_requested() -> bool:
    from app.config import VAULT_INCOMING_MODE

    return VAULT_INCOMING_MODE != "off"


def vault_root() -> Path | None:
    root = resolve_vault_root()
    return Path(root) if root else None


def originals_dir() -> Path | None:
    r = vault_root()
    return r / REL_ORIGINALS if r else None


def incoming_dir() -> Path | None:
    r = vault_root()
    return r / REL_INCOMING if r else None


def pending_dir() -> Path | None:
    r = vault_root()
    return r / REL_PENDING if r else None


def ensure_vault_layout() -> None:
    for d in (originals_dir(), incoming_dir(), pending_dir()):
        if d is not None:
            d.mkdir(parents=True, exist_ok=True)


def vault_writable() -> bool:
    od = originals_dir()
    if od is None:
        return False
    try:
        ensure_vault_layout()
        probe = od / f".write_probe_{uuid.uuid4().hex}"
        probe.write_bytes(b"")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def absolute_from_vault_relative(rel: str) -> Path | None:
    root = vault_root()
    if root is None or not rel or not str(rel).strip():
        return None
    rel_norm = str(rel).replace("\\", "/").lstrip("/")
    if ".." in rel_norm.split("/"):
        return None
    p = (root / rel_norm).resolve()
    try:
        p.relative_to(root.resolve())
    except ValueError:
        return None
    return p


def _default_upload_name(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return "upload.pdf"
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"):
        return f"upload{ext}"
    return "upload.bin"


def _sanitize_filename(name: str, default: str) -> str:
    base = Path(name).name.strip()
    if not base or base in (".", ".."):
        return default
    return base


def _vault_relative(*parts: str) -> str:
    return "/".join(parts)


def _handle_save_error(exc: Exception, context: str) -> tuple[None, None]:
    from app.config import VAULT_INGEST_REQUIRE_WRITE

    logger.warning("vault save failed (%s): %s", context, exc)
    if VAULT_INGEST_REQUIRE_WRITE:
        raise
    return None, None


def save_original(doc_id: str, filename: str, data: bytes) -> tuple[str | None, str | None]:
    try:
        ensure_vault_layout()
        od = originals_dir()
        if od is None:
            return None, None
        safe_name = _sanitize_filename(filename, _default_upload_name(filename))
        dest_dir = od / doc_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / safe_name
        dest.write_bytes(data)
        rel = _vault_relative(REL_ORIGINALS, doc_id, safe_name)
        return rel, str(dest.resolve())
    except Exception as e:
        return _handle_save_error(e, f"save_original doc_id={doc_id}")


def save_text_snapshot(doc_id: str, utf8_bytes: bytes) -> tuple[str | None, str | None]:
    try:
        ensure_vault_layout()
        od = originals_dir()
        if od is None:
            return None, None
        dest_dir = od / doc_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "extracted.txt"
        dest.write_bytes(utf8_bytes)
        rel = _vault_relative(REL_ORIGINALS, doc_id, "extracted.txt")
        return rel, str(dest.resolve())
    except Exception as e:
        return _handle_save_error(e, f"save_text_snapshot doc_id={doc_id}")
