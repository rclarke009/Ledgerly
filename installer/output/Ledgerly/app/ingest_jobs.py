"""Ingest background job model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IngestJobKind(str, Enum):
    TEXT = "text"
    PDF = "pdf"
    IMAGE = "image"


class IngestJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class IngestJob:
    id: str
    kind: IngestJobKind
    status: IngestJobStatus = IngestJobStatus.PENDING
    filename: str | None = None
    temp_path: str | None = None
    doc_id: str = ""
    title: str | None = None
    source: str | None = None
    chunk_size: int = 800
    chunk_overlap: int = 100
    confirm_duplicate_content: bool = False
    tags: list[str] | None = None
    account_id: str | None = None
    text_content: str | None = None
    pdf_text_mode: str = "auto"
    keep_incoming_original_rel: str | None = None
    stage: str = "queued"
    progress_pct: float = 0.0
    eta_seconds: int | None = None
    estimated_completion_at: Any = None
    error: str | None = None
    result: dict[str, Any] | None = None
    _embed_started_at: float | None = field(default=None, repr=False)
