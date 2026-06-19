"""Background ask job model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AskJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class AskJob:
    id: str
    question: str
    top_k: int = 5
    doc_id: str | None = None
    tag: str | None = None
    use_rag: bool = True
    conversation_id: str | None = None
    status: AskJobStatus = AskJobStatus.PENDING
    stage: str = "queued"
    progress_pct: float = 0.0
    eta_seconds: int | None = None
    error: str | None = None
    answer: str | None = None
    top_chunks: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    charts: list[dict[str, Any]] = field(default_factory=list)
    route: str | None = None
    turn_id: str | None = None
    related_documents: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = 0.0
