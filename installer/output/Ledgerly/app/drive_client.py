"""Google Drive client stub."""

from __future__ import annotations


class DriveClientError(Exception):
    pass


async def list_and_export_docs(*args, **kwargs):
    raise DriveClientError("Google Drive not configured")
