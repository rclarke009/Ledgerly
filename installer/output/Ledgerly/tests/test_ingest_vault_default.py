"""Tests for zero-config default vault on PDF ingest."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.db import create_db
from app.main import app


class _MockEmbedder:
    model = "nomic-embed-text"
    dim = 768

    async def embed_many(self, texts, **kwargs):
        return [[0.0] * self.dim for _ in texts]


MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Contents 4 0 R >>\nendobj\n"
    b"4 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 100 700 Td (Hello) Tj ET\nendstream\nendobj\n"
    b"xref\n0 5\n0000000000 65535 f \n"
    b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n0\n%%EOF\n"
)

SAMPLE_TEXT = (
    "Certificate of deposit account summary. Principal balance $10,000. "
    "Annual percentage yield 4.50 percent. Maturity date March 15, 2026."
)


@pytest.fixture
def client_with_db(tmp_path, monkeypatch):
    db_file = tmp_path / "ingest_vault.sqlite"
    conn = sqlite3.connect(str(db_file))
    create_db(conn)
    conn.close()
    app.state.use_postgres = False
    app.state.db_path = str(db_file)

    vault_root = tmp_path / "vault"
    monkeypatch.setattr(main_module, "HttpEmbedder", lambda *a, **k: _MockEmbedder())
    monkeypatch.setattr(main_module, "INGEST_STRUCTURED_ENABLED", False)

    async def fake_facts(text, title):
        return None

    monkeypatch.setattr(main_module, "extract_document_facts", fake_facts)

    async def fake_pdf(raw, mode):
        return SAMPLE_TEXT

    monkeypatch.setattr(main_module, "resolve_pdf_for_ingest", fake_pdf)
    monkeypatch.setattr("app.config.LEDGERLY_ORIGINALS_VAULT", "")

    def _resolve_root():
        from app.config import LEDGERLY_ORIGINALS_VAULT

        if LEDGERLY_ORIGINALS_VAULT:
            return LEDGERLY_ORIGINALS_VAULT
        return str(vault_root.resolve())

    monkeypatch.setattr("app.vault_settings_store.resolve_vault_root", _resolve_root)

    yield TestClient(app), vault_root
    app.state.db_path = None


def test_ingest_pdf_saves_default_vault_and_preview(client_with_db):
    client, vault_root = client_with_db
    doc_id = "vault-preview-doc"

    res = client.post(
        "/ingest/pdf",
        data={"doc_id": doc_id, "title": "Test PDF"},
        files={"file": ("statement.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["doc_id"] == doc_id
    assert body["has_openable_original"] is True
    assert body["original_vault_path"]
    assert body["original_vault_path"].startswith("originals/")
    assert body["source"]
    assert str(vault_root) in body["source"]

    saved = Path(body["source"])
    assert saved.is_file()
    assert saved.read_bytes() == MINIMAL_PDF

    list_res = client.get("/documents")
    assert list_res.status_code == 200
    match = next(d for d in list_res.json()["documents"] if d["doc_id"] == doc_id)
    assert match["has_openable_original"] is True
    assert match["original_vault_path"] == body["original_vault_path"]


def test_ingest_pdf_env_vault_override(tmp_path, monkeypatch):
    db_file = tmp_path / "ingest_env.sqlite"
    conn = sqlite3.connect(str(db_file))
    create_db(conn)
    conn.close()
    app.state.use_postgres = False
    app.state.db_path = str(db_file)

    custom_vault = tmp_path / "custom_vault"
    monkeypatch.setattr(main_module, "HttpEmbedder", lambda *a, **k: _MockEmbedder())
    monkeypatch.setattr(main_module, "INGEST_STRUCTURED_ENABLED", False)
    async def no_facts(text, title):
        return None

    monkeypatch.setattr(main_module, "extract_document_facts", no_facts)

    async def fake_pdf(raw, mode):
        return SAMPLE_TEXT

    monkeypatch.setattr(main_module, "resolve_pdf_for_ingest", fake_pdf)
    monkeypatch.setattr("app.config.LEDGERLY_ORIGINALS_VAULT", str(custom_vault.resolve()))

    client = TestClient(app)
    doc_id = "env-vault-doc"
    res = client.post(
        "/ingest/pdf",
        data={"doc_id": doc_id},
        files={"file": ("letter.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["has_openable_original"] is True
    assert str(custom_vault.resolve()) in body["source"]
    assert Path(body["source"]).is_file()
    app.state.db_path = None
