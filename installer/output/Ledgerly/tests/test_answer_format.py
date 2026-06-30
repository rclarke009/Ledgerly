"""Unit tests for answer markdown layout and structured tail parsing."""

from __future__ import annotations

from app.answer_format import merge_structured_to_response, split_structured


def test_split_structured_canonical_json_tail():
    raw = (
        "The maturity date is 2026-09-15.\n\n"
        "---LEDGERLY_STRUCTURED---\n"
        '{"tables": [], "charts": []}'
    )
    body, tail = split_structured(raw)
    assert body == "The maturity date is 2026-09-15."
    assert tail == {"tables": [], "charts": []}


def test_split_structured_loose_marker_and_pseudo_yaml():
    raw = (
        "The maturity date on the March 2026 CD is 2026-09-15.\n\n"
        "---\n"
        "LEDGERLY_STRUCTURED\n"
        "tables: []\n"
        "charts: []"
    )
    body, tail = split_structured(raw)
    assert body == "The maturity date on the March 2026 CD is 2026-09-15."
    assert tail == {"tables": [], "charts": []}


def test_split_structured_strips_marker_even_when_tail_unparseable():
    raw = "Short answer.\n\n---\nLEDGERLY_STRUCTURED\nnot valid json"
    body, tail = split_structured(raw)
    assert body == "Short answer."
    assert tail is None


def test_split_structured_no_marker_returns_full_text():
    raw = "Plain answer with no structured tail."
    body, tail = split_structured(raw)
    assert body == raw
    assert tail is None


def test_merge_structured_to_response_empty_tail():
    answer, tables, charts = merge_structured_to_response("Hello", {"tables": [], "charts": []})
    assert answer == "Hello"
    assert tables == []
    assert charts == []
