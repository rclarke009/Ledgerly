"""Vault settings store — env vault, default app-local vault, optional UI file settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_VAULT_REL = ".ledgerly/vault"


def effective_vault_root_source() -> str:
    from app.config import LEDGERLY_ORIGINALS_VAULT

    if LEDGERLY_ORIGINALS_VAULT:
        return "env"
    return "default"


def file_settings_snapshot() -> dict[str, Any]:
    return {}


def resolve_vault_incoming_mode() -> str:
    from app.config import VAULT_INCOMING_MODE

    return VAULT_INCOMING_MODE


def resolve_vault_root() -> str | None:
    from app.config import LEDGERLY_ORIGINALS_VAULT

    if LEDGERLY_ORIGINALS_VAULT:
        return LEDGERLY_ORIGINALS_VAULT
    return str((Path.cwd() / DEFAULT_VAULT_REL).resolve())


def vault_root_is_from_env() -> bool:
    from app.config import LEDGERLY_ORIGINALS_VAULT

    return bool(LEDGERLY_ORIGINALS_VAULT)


def write_vault_settings_file(root: str | None, incoming_mode: str) -> None:
    return None
