"""Native folder picker stub."""

from __future__ import annotations


class NativeFolderDialogUnavailable(Exception):
    pass


def pick_native_folder() -> str | None:
    raise NativeFolderDialogUnavailable("Native folder picker unavailable")
