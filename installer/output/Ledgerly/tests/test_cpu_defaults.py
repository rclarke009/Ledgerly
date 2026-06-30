"""Tests for conservative Ollama thread defaults."""

from __future__ import annotations

import pytest

from app import cpu_defaults


@pytest.mark.parametrize(
    ("cpus", "expected"),
    [
        (1, 1),
        (2, 1),
        (4, 2),
        (8, 4),
        (16, 8),
    ],
)
def test_default_ollama_num_threads(monkeypatch: pytest.MonkeyPatch, cpus: int, expected: int) -> None:
    monkeypatch.setattr(cpu_defaults, "available_cpu_count", lambda: cpus)
    assert cpu_defaults.default_ollama_num_threads() == expected


def test_available_cpu_count_falls_back_to_os_cpu_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(cpu_defaults.os, "sched_getaffinity", raising=False)
    monkeypatch.setattr(cpu_defaults.os, "cpu_count", lambda: 6)
    assert cpu_defaults.available_cpu_count() == 6


def test_available_cpu_count_prefers_sched_getaffinity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cpu_defaults.os,
        "sched_getaffinity",
        lambda _pid: {0, 1, 2, 3},
        raising=False,
    )
    monkeypatch.setattr(cpu_defaults.os, "cpu_count", lambda: 16)
    assert cpu_defaults.available_cpu_count() == 4
