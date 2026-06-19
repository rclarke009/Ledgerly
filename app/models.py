## 3. Request and response models (Pydantic)

# Define Pydantic models for the two main flows. 
# For **ingest:** a request body with at least `text` 
# (required), and optional `doc_id`, `title`, `source`, 
# and chunking options (e.g. `chunk_size`, `chunk_overlap`). 
# Define a response that includes `doc_id`, `num_chunks`, and 
# whatever embedding metadata you plan to return. 
# 
# For **ask:** a request with `question`, optional `top_k` and optional 
# `doc_id` (to restrict search to one document), and a response with 
# `answer` and a list of retrieved chunks (each with something like `chunk_id`, 
# `doc_id`, `score`, and a short `content_snippet`). (made that into RetrievedChunk class)

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.answer_format import AnswerChart, AnswerTable

# --- Financial (Private Cash Assistant) ---

class AccountCreate(BaseModel):
    name: str = Field(..., min_length=1)
    type: str | None = None
    institution: str | None = None
    document_id: str | None = None


class AccountUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    institution: str | None = None
    document_id: str | None = None


class AccountResponse(BaseModel):
    id: str
    name: str
    type: str | None = None
    institution: str | None = None
    document_id: str | None = None
    created_at: int


class PositionCreate(BaseModel):
    account_id: str = Field(..., min_length=1)
    asset_type: str = Field(..., min_length=1)
    description: str | None = None
    principal: float | None = None
    rate_apr: float | None = None
    maturity_date: str | None = None
    document_id: str | None = None
    start_date: str | None = None
    next_action: str | None = None
    liquidity_note: str | None = None


class PositionUpdate(BaseModel):
    description: str | None = None
    principal: float | None = None
    rate_apr: float | None = None
    maturity_date: str | None = None
    document_id: str | None = None
    start_date: str | None = None
    next_action: str | None = None
    liquidity_note: str | None = None


class PositionResponse(BaseModel):
    id: str
    account_id: str
    asset_type: str
    description: str | None = None
    principal: float | None = None
    rate_apr: float | None = None
    maturity_date: str | None = None
    document_id: str | None = None
    start_date: str | None = None
    next_action: str | None = None
    liquidity_note: str | None = None
    created_at: int
    updated_at: int


class ObligationCreate(BaseModel):
    description: str = Field(..., min_length=1)
    due_date: str = Field(..., min_length=1)
    amount_estimate: float | None = None
    priority: str | None = None
    document_id: str | None = None


class ObligationUpdate(BaseModel):
    description: str | None = None
    due_date: str | None = None
    amount_estimate: float | None = None
    priority: str | None = None
    document_id: str | None = None


class ObligationResponse(BaseModel):
    id: str
    description: str
    due_date: str
    amount_estimate: float | None = None
    priority: str | None = None
    document_id: str | None = None
    created_at: int


class IraOverviewCreate(BaseModel):
    account_name: str = Field(..., min_length=1)
    institution: str | None = None
    account_type: str | None = Field(
        default=None, description="e.g. traditional, roth — awareness only"
    )
    balance_estimate: float | None = None
    rmd_note: str | None = None
    next_relevant_date: str | None = Field(
        default=None, description="RMD, statement, or review date (YYYY-MM-DD)"
    )
    document_id: str | None = None


class IraOverviewUpdate(BaseModel):
    account_name: str | None = None
    institution: str | None = None
    account_type: str | None = None
    balance_estimate: float | None = None
    rmd_note: str | None = None
    next_relevant_date: str | None = None
    document_id: str | None = None


class IraOverviewResponse(BaseModel):
    id: str
    account_name: str
    institution: str | None = None
    account_type: str | None = None
    balance_estimate: float | None = None
    rmd_note: str | None = None
    next_relevant_date: str | None = None
    document_id: str | None = None
    created_at: int
    updated_at: int


class TriggerEventResponse(BaseModel):
    id: str
    trigger_type: str
    entity_type: str
    entity_id: str
    event_date: str | None = None
    evaluated_at: int
    status: str


# Sources used in advice (discriminated: user_data | web)
class UserDataSource(BaseModel):
    type: Literal["user_data"] = "user_data"
    entity_type: str = Field(..., description="account | position | obligation")
    id: str
    label: str = Field(..., description="Human-readable short label")


class WebSource(BaseModel):
    type: Literal["web"] = "web"
    quote: str | None = None
    url: str | None = None
    source_name: str | None = None


AdviceSource = UserDataSource | WebSource


class DecisionResponse(BaseModel):
    status: Literal["no_action_required", "actionable"] = Field(...)
    triggers: list[TriggerEventResponse] = Field(default_factory=list)
    memo: str | None = None
    sources: list[UserDataSource | WebSource] = Field(default_factory=list)
    openai_advice: list[str] = Field(
        default_factory=list,
        description="Operational decision memo lines (one per maturity trigger); empty if not configured.",
    )
    rate_comparisons: list[str] = Field(
        default_factory=list,
        description="User rate vs benchmark summaries when maturity triggers fire.",
    )
    liquidity_notes: list[str] = Field(
        default_factory=list,
        description="Cross-check of maturing principal vs nearby obligations.",
    )


class DecisionHistoryItem(BaseModel):
    id: str
    evaluated_at: int
    status: str
    memo: str | None = None
    trigger_ids: str | None = None


class AskHistoryItem(BaseModel):
    id: str
    job_id: str | None = None
    asked_at: int
    status: Literal["pending", "complete", "failed"]
    question: str
    answer: str | None = None
    tables: list[AnswerTable] = Field(default_factory=list)
    charts: list[AnswerChart] = Field(default_factory=list)
    route: str | None = None
    doc_filter: str | None = None
    error: str | None = None
    conversation_id: str | None = None
    parent_id: str | None = None
    related_documents: list["RelatedDocument"] = Field(default_factory=list)


class DashboardMaturityItem(BaseModel):
    id: str
    account_id: str
    account_name: str
    institution: str | None = None
    asset_type: str
    description: str | None = None
    principal: float | None = None
    rate_apr: float | None = None
    maturity_date: str | None = None
    document_id: str | None = None
    start_date: str | None = None
    next_action: str | None = None
    liquidity_note: str | None = None
    label: str
    days_until: int | None = None


class DashboardLadderItem(DashboardMaturityItem):
    """CD ladder row for Home table view."""


class DashboardIraItem(BaseModel):
    id: str
    account_name: str
    institution: str | None = None
    account_type: str | None = None
    balance_estimate: float | None = None
    rmd_note: str | None = None
    next_relevant_date: str | None = None
    days_until: int | None = None


class DashboardObligationItem(BaseModel):
    id: str
    description: str
    due_date: str
    amount_estimate: float | None = None
    priority: str | None = None
    document_id: str | None = None
    days_until: int | None = None


class ExtractedPosition(BaseModel):
    institution: str | None = None
    asset_type: str = "CD"
    description: str | None = None
    principal: float | None = None
    rate_apr: float | None = None
    maturity_date: str | None = None
    confidence: str | None = None


class ExtractedObligation(BaseModel):
    description: str
    due_date: str | None = None
    amount_estimate: float | None = None
    priority: str | None = None
    confidence: str | None = None


class PendingExtractionItem(BaseModel):
    document_id: str
    title: str | None = None
    extraction: ExtractedPosition


class RecentlyAddedItem(BaseModel):
    kind: Literal["position", "obligation"]
    id: str
    label: str
    document_id: str | None = None
    created_at: int


class PendingObligationExtractionItem(BaseModel):
    document_id: str
    title: str | None = None
    extraction: ExtractedObligation


class DashboardResponse(BaseModel):
    status: Literal["no_action_required", "actionable"]
    actionable: bool
    memo: str
    trigger_count: int = 0
    trigger_days_ahead: int = 30
    renewal_tips: list[str] = Field(default_factory=list)
    next_maturity: DashboardMaturityItem | None = None
    upcoming_maturing: list[DashboardMaturityItem] = Field(default_factory=list)
    overdue_maturing: list[DashboardMaturityItem] = Field(default_factory=list)
    upcoming_obligations: list[DashboardObligationItem] = Field(default_factory=list)
    overdue_obligations: list[DashboardObligationItem] = Field(default_factory=list)
    totals_by_asset_type: dict[str, float] = Field(default_factory=dict)
    pending_extractions: list[PendingExtractionItem] = Field(default_factory=list)
    pending_obligation_extractions: list[PendingObligationExtractionItem] = Field(default_factory=list)
    recently_added: list[RecentlyAddedItem] = Field(default_factory=list)
    days_window: int = 365
    ladder_positions: list[DashboardLadderItem] = Field(
        default_factory=list,
        description="All open CD-like positions sorted by maturity (ladder table).",
    )
    ira_overview: list[DashboardIraItem] = Field(
        default_factory=list,
        description="IRA awareness rows (not investment advice).",
    )


class ConfirmExtractionRequest(BaseModel):
    document_id: str = Field(..., min_length=1)
    accept: bool
    overrides: ExtractedPosition | None = None


class ConfirmObligationExtractionRequest(BaseModel):
    document_id: str = Field(..., min_length=1)
    accept: bool
    overrides: ExtractedObligation | None = None


class ConfirmObligationExtractionResponse(BaseModel):
    accepted: bool
    obligation: ObligationResponse | None = None
    message: str | None = None


class ResolvePositionRequest(BaseModel):
    action: Literal["renewed", "closed"]
    new_maturity_date: str | None = Field(
        default=None,
        description="Required when action is renewed; YYYY-MM-DD",
    )


class ResolveObligationRequest(BaseModel):
    action: Literal["paid"] = "paid"


class ConfirmExtractionResponse(BaseModel):
    accepted: bool
    position: PositionResponse | None = None
    account_id: str | None = None
    message: str | None = None


class RemoteLogEventPayload(BaseModel):
    """Sanitized payload for remote log (no PII). Sent to Supabase Edge Function when REMOTE_LOG_URL is set."""

    timestamp: str
    level: Literal["ERROR", "WARNING", "INFO"]
    message: str
    route: str | None = None
    request_id: str | None = None
    trace_id: str | None = None
    duration_ms: int | None = None
    error_type: str | None = None
    stack_trace: str | None = None
    instance_id: str | None = None


# --- Document / RAG (existing) ---

class ChunkingOptions(BaseModel):
    strategy: Literal["chars", "sentences"] = "chars"
    chunk_size: int = Field(default=800, description= "Chunk size")
    chunk_overlap: int = Field(default=100, description="Chunk overlap")

    @model_validator(mode="after")
    def check_chunking_bounds(self)->"ChunkingOptions":
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be greater than or equal to 0")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        return self

class IngestRequest (BaseModel):
    text: str = Field(..., min_length=1,description="Text to ingest")
    doc_id: str | None = None
    title: str | None = None
    source: str | None = None
    tags: list[str] | None = Field(default=None, description="Optional tags for grouping (e.g. 2024, Checking)")
    chunking_options: ChunkingOptions | None = None
    confirm_duplicate_content: bool = Field(
        default=False,
        description="If True, allow ingesting the same text/PDF again under a different doc_id (skip duplicate-content warning).",
    )
    account_id: str | None = Field(default=None, description="Link document to this account id")

    @model_validator(mode='after')
    def set_defaults(self) -> "IngestRequest":
        doc_id = self.doc_id if self.doc_id is not None else str(uuid.uuid4())
        chunking_options = self.chunking_options if self.chunking_options is not None else ChunkingOptions()
        return self.model_copy(update={"doc_id":doc_id, "chunking_options":chunking_options})

class IngestResponse(BaseModel):
    doc_id: str = Field(..., description="doc_id")
    num_chunks: int = Field(..., description="Number of chunks")
    embedding_model: str = Field(..., description="Embedding model")
    dim: int = Field(..., description="Embedding vector dimension")
    facts_learned: list[str] | None = Field(
        default=None,
        description="Bullet facts extracted during ingest when INGEST_FACTS_ENABLED is on",
    )
    extracted_position: ExtractedPosition | None = Field(
        default=None,
        description="Structured position suggestion from ingest when INGEST_STRUCTURED_ENABLED is on",
    )
    extracted_obligation: ExtractedObligation | None = Field(
        default=None,
        description="Structured obligation suggestion from ingest when INGEST_STRUCTURED_ENABLED is on",
    )
    auto_tracked_position: PositionResponse | None = Field(
        default=None,
        description="Position created automatically during ingest when INGEST_AUTO_TRACK_ENABLED is on",
    )
    auto_tracked_obligation: ObligationResponse | None = Field(
        default=None,
        description="Obligation created automatically during ingest when INGEST_AUTO_TRACK_ENABLED is on",
    )
    source: str | None = Field(
        default=None,
        description="Effective source path or label stored with the document",
    )
    original_vault_path: str | None = Field(
        default=None,
        description="Relative vault path of saved original, when vault is used",
    )
    has_openable_original: bool = Field(
        default=False,
        description="True when the original file exists on disk and can be previewed or opened",
    )


class IngestJobEnqueueItem(BaseModel):
    job_id: str
    filename: str | None = None


class IngestEnqueueResponse(BaseModel):
    jobs: list[IngestJobEnqueueItem]


class IngestJobStatusResponse(BaseModel):
    id: str
    status: str
    kind: str
    filename: str | None = None
    created_at: datetime
    updated_at: datetime
    progress_pct: float
    stage: str
    eta_seconds: int | None = None
    estimated_completion_at: datetime | None = None
    error: str | None = None
    result: dict[str, Any] | None = None


class AskJobEnqueueResponse(BaseModel):
    job_id: str
    estimated_wait_sec: int = Field(default=600, description="Rough wait hint for background ask")


class AskJobStatusResponse(BaseModel):
    id: str
    status: str
    stage: str
    progress_pct: float
    eta_seconds: int | None = None
    error: str | None = None
    answer: str | None = None
    route: str | None = None
    top_chunks: list[dict[str, Any]] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    charts: list[dict[str, Any]] = Field(default_factory=list)
    conversation_id: str | None = None
    turn_id: str | None = None
    related_documents: list["RelatedDocument"] = Field(default_factory=list)


class RelatedDocument(BaseModel):
    doc_id: str
    title: str
    reason: Literal["pinned", "retrieved", "topic_boost"]


class AskRequest(BaseModel):
    question: str = Field(..., description="Question from user")
    conversation_id: str | None = Field(
        default=None,
        description="Continue an existing conversation; omit to start a new one",
    )
    top_k: int = Field(default=5, description="Will pull the top __ matches")
    doc_id: str | None = Field(default=None, description="Search only within this document")
    doc_ids: list[str] | None = Field(default=None, description="Search only within these document ids")
    tag: str | None = Field(default=None, description="Search only within documents with this tag")
    use_rag: bool = True

class RetrievedChunk(BaseModel):
    chunk_id: str = Field(..., description="chunk_id")
    doc_id: str = Field(..., description="doc_id")
    score: float = Field(..., description="score")
    content_snippet: str = Field(..., description="content_snippet")

class AskResponse(BaseModel):
    answer: str = Field(
        ...,
        description="Markdown answer; structured JSON tail stripped when valid. If parsing fails, full raw model text.",
    )
    top_chunks: list[RetrievedChunk] = Field(..., description="top _ chunks")
    tables: list[AnswerTable] = Field(default_factory=list, description="Structured tables from model tail, if any")
    charts: list[AnswerChart] = Field(default_factory=list, description="Chart specs from model tail, if any")
    prompt_tokens_estimate: int | None = Field(default= None, description="prompt tokens estimate") # (stub ok)
    conversation_id: str | None = None
    turn_id: str | None = None
    related_documents: list[RelatedDocument] = Field(default_factory=list)


# Max characters for template=custom user question (OpenAI general path, no RAG).
ASK_GENERAL_CUSTOM_QUESTION_MAX_LEN = 4000


# General-path (OpenAI only): templated params or validated custom question (no documents).
class AskGeneralRequest(BaseModel):
    template: Literal["cd_advice", "cd_rates_summary", "custom"] = Field(
        ...,
        description="Whitelisted template; server-built prompts or custom question sent to OpenAI.",
    )
    amount: float | None = Field(default=None, description="For cd_advice: principal amount (no identifiers).")
    term_months: int | None = Field(default=None, description="For cd_advice: CD term in months.")
    question: str | None = Field(
        default=None,
        description="For custom: user question only; no documents are included.",
    )

    @model_validator(mode="after")
    def _validate_ask_general_template(self) -> "AskGeneralRequest":
        if self.template == "custom":
            q = (self.question or "").strip()
            if not q:
                raise ValueError("question is required for custom template")
            if len(q) > ASK_GENERAL_CUSTOM_QUESTION_MAX_LEN:
                raise ValueError(
                    f"question must be at most {ASK_GENERAL_CUSTOM_QUESTION_MAX_LEN} characters"
                )
            self.question = q
        else:
            self.question = None
        return self


class AskGeneralResponse(BaseModel):
    answer: str = Field(
        ...,
        description="Markdown answer from OpenAI; structured JSON tail stripped when valid.",
    )
    tables: list[AnswerTable] = Field(default_factory=list)
    charts: list[AnswerChart] = Field(default_factory=list)


class AskImageResponse(BaseModel):
    answer: str = Field(..., description="Report-style text from LLaVA (vision model) for the image.")


class WarmupResponse(BaseModel):
    status: Literal["started", "warming", "ready", "skipped"] = Field(...)
    profile: Literal["ask", "ingest"] = Field(...)


class WarmupStatusResponse(BaseModel):
    ask: Literal["idle", "running", "ready"] = Field(...)
    ingest: Literal["idle", "running", "ready"] = Field(...)
    ready_until: dict[str, int | None] = Field(default_factory=dict)


class DocumentSummary(BaseModel):
    doc_id: str = Field(..., description="Document id")
    title: str | None = Field(default=None, description="Title")
    source: str | None = Field(default=None, description="Source")
    created_at: int = Field(..., description="Unix timestamp")
    num_chunks: int = Field(..., description="Number of chunks")
    snippet: str | None = Field(default=None, description="First ~250 chars of first chunk")
    tags: list[str] = Field(default_factory=list, description="Tags for grouping/filtering")
    linked_account_ids: list[str] = Field(default_factory=list, description="Account IDs that reference this document")
    facts_learned: list[str] | None = Field(
        default=None,
        description="Bullet facts from ingest (learning mode) when enabled",
    )
    original_vault_path: str | None = Field(
        default=None,
        description="Path of saved original relative to LEDGERLY_ORIGINALS_VAULT, if vault is used",
    )
    has_openable_original: bool = Field(
        default=False,
        description="True when the original file exists on disk and can be previewed or opened",
    )


class DocumentUpdateRequest(BaseModel):
    """Optional fields for PATCH /documents/{doc_id}. Omit a field to leave it unchanged."""

    tags: list[str] | None = Field(default=None, description="Replace document tags with this list")
    account_id: str | None = Field(default=None, description="Set linked account (null = unlink all)")
    source: str | None = Field(
        default=None,
        description="Stored source label or absolute file path (null clears)",
    )


class DocumentsListResponse(BaseModel):
    documents: list[DocumentSummary] = Field(..., description="List of ingested documents")


class VaultStatusResponse(BaseModel):
    enabled: bool
    watcher_mode: str = Field(..., description="off | watch_auto | watch_review")
    root: str | None = None
    writable: bool | None = Field(
        default=None,
        description="Whether the vault root exists and passed a probe write when enabled",
    )
    originals_dir: str | None = None
    incoming_dir: str | None = None
    pending_dir: str | None = None
    root_source: str | None = Field(default=None, description="env | file when vault enabled")


class VaultSettingsPutRequest(BaseModel):
    root: str | None = Field(default=None, description="Absolute vault root (empty disables file-based vault)")
    incoming_mode: str = Field(..., description="off | watch_auto | watch_review")


class VaultSettingsGetResponse(BaseModel):
    effective_root: str | None = None
    effective_incoming_mode: str = "off"
    root_source: str | None = Field(default=None, description="env | file | null")
    file_root: str | None = None
    file_incoming_mode: str | None = None
    writable: bool | None = None
    originals_dir: str | None = None
    incoming_dir: str | None = None
    pending_dir: str | None = None
    env_controls_settings: bool = Field(
        default=False,
        description="True when LEDGERLY_ORIGINALS_VAULT is set (UI cannot override)",
    )


class VaultSettingsConfigAllowedResponse(BaseModel):
    """Whether this HTTP client may PUT /vault/settings (loopback or ALLOW_REMOTE_VAULT_SETTINGS)."""

    allowed: bool


class VaultRootVerifyRequest(BaseModel):
    root: str = Field(default="", description="Candidate vault root path to validate")


class VaultRootVerifyResponse(BaseModel):
    valid: bool
    resolved_root: str | None = None
    incoming_dir: str | None = None
    pending_dir: str | None = None
    originals_dir: str | None = None
    detail: str | None = None


class VaultNativePickFolderResponse(BaseModel):
    path: str | None = None
    cancelled: bool = False


class VaultIncomingScanResponse(BaseModel):
    enqueued: int = Field(default=0, description="Ingest jobs queued from incoming/")
    moved_to_pending: int = Field(default=0, description="Files moved to pending/ (watch_review)")
    skipped: int = Field(default=0)
    errors: list[str] = Field(default_factory=list)


class VaultPendingIngestRequest(BaseModel):
    """Ingest one file from vault/pending/ by path under that folder (POSIX, may include subdirs)."""

    relative_path: str = Field(
        ...,
        min_length=1,
        description="Relative path under pending/, e.g. taxes/2024.pdf",
    )


class IngestGoogleDriveRequest(BaseModel):
    """Request to ingest documents from Google Drive (read-only)."""

    folder_id: str | None = Field(default=None, description="Limit to files in this folder")
    file_ids: list[str] | None = Field(default=None, description="If set, only these file IDs (folder_id ignored)")


class IngestGoogleDriveResponse(BaseModel):
    """Result of Google Drive sync."""

    ingested: int = Field(..., description="Number of documents ingested")
    skipped: int = Field(default=0, description="Number skipped (e.g. duplicate doc_id)")
    errors: list[str] = Field(default_factory=list, description="Error messages for failed docs")
    doc_ids: list[str] = Field(default_factory=list, description="doc_ids that were ingested")
