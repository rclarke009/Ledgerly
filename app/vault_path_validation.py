"""Vault path validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VaultRootValidation:
    valid: bool
    resolved_root: str | None = None
    incoming_dir: str | None = None
    pending_dir: str | None = None
    originals_dir: str | None = None
    detail: str | None = None


def validate_vault_root_path(path: str) -> VaultRootValidation:
    s = (path or "").strip()
    if not s:
        return VaultRootValidation(valid=False, detail="Path required")
    try:
        p = Path(s).expanduser().resolve()
    except (OSError, RuntimeError) as e:
        return VaultRootValidation(valid=False, detail=str(e))
    if not p.is_absolute():
        return VaultRootValidation(valid=False, detail="Path must be absolute")
    root = str(p)
    return VaultRootValidation(
        valid=True,
        resolved_root=root,
        incoming_dir=str(p / "incoming"),
        pending_dir=str(p / "pending"),
        originals_dir=str(p / "originals"),
    )
