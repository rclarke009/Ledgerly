#!/usr/bin/env python3
"""Build Ledgerly-Portable.zip without Docker (same layout as build-portable.sh)."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

# Top-level names excluded from copy (same as build-portable.sh `case` list).
SKIP_TOP_LEVEL = frozenset(
    {".env", ".git", "__pycache__", ".venv", "installer", ".idea", ".vscode"}
)
DOTFILES_TO_INCLUDE = (".dockerignore", ".env.example", ".env.portable-xps15.example")
LOCAL_DATA_SUFFIXES = (".sqlite", ".db", ".dump")
ZIP_NAME = "Ledgerly-Portable.zip"


def _copy_tree(src: Path, dest: Path) -> None:
    shutil.copytree(
        src,
        dest,
        dirs_exist_ok=False,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".env", ".venv"),
    )


def main() -> int:
    installer_dir = Path(__file__).resolve().parent
    root = installer_dir.parent
    out_dir = installer_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / ZIP_NAME

    with tempfile.TemporaryDirectory() as td:
        stage_root = Path(td)
        stage_app = stage_root / "Ledgerly"
        stage_app.mkdir(parents=True)

        for path in root.iterdir():
            name = path.name
            if name in SKIP_TOP_LEVEL:
                continue
            if name.startswith("."):
                continue
            if path.suffix in LOCAL_DATA_SUFFIXES:
                continue
            dest = stage_app / name
            if path.is_dir():
                _copy_tree(path, dest)
            elif path.is_file():
                shutil.copy2(path, dest)

        for dot in DOTFILES_TO_INCLUDE:
            src = root / dot
            if src.is_file():
                shutil.copy2(src, stage_app / dot)

        for d in list(stage_app.rglob("__pycache__")) + list(stage_app.rglob(".venv")):
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)

        for suffix in LOCAL_DATA_SUFFIXES:
            for f in stage_app.rglob(f"*{suffix}"):
                if f.is_file():
                    f.unlink(missing_ok=True)
        for f in stage_app.rglob(".env"):
            if f.is_file():
                f.unlink(missing_ok=True)
        (stage_app / "payload.json").unlink(missing_ok=True)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in stage_app.rglob("*"):
                if not f.is_file():
                    continue
                if f.name == ".DS_Store" or f.suffix in LOCAL_DATA_SUFFIXES:
                    continue
                if f.name == ".env":
                    continue
                arc = f.relative_to(stage_root)
                zf.write(f, arc.as_posix())

    print(f"Built: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
