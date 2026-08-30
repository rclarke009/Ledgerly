"""Portable vs default ingest pacing env fallbacks."""

from __future__ import annotations

import pytest

from app.config import default_embed_inter_batch_sleep, default_ingest_queue_sleep


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("portable", "1"),
        ("low_spec", "1"),
        ("", "0"),
        ("full", "0"),
    ],
)
def test_default_embed_inter_batch_sleep(profile: str, expected: str) -> None:
    assert default_embed_inter_batch_sleep(profile) == expected


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("portable", "8"),
        ("low_spec", "8"),
        ("", "3"),
        ("full", "3"),
    ],
)
def test_default_ingest_queue_sleep(profile: str, expected: str) -> None:
    assert default_ingest_queue_sleep(profile) == expected
