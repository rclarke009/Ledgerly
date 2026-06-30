"""Tests for character chunking with offsets."""

from app.chunking import TextChunk, chunk_text_chars


def test_chunk_text_chars_offsets_and_overlap():
    text = "abcdefghijklmnopqrstuvwxyz"
    chunks = chunk_text_chars(text, chunk_size=10, chunk_overlap=2)
    assert len(chunks) == 3
    assert chunks[0] == TextChunk(chunk_index=0, content="abcdefghij", start_offset=0, end_offset=10)
    assert chunks[1] == TextChunk(chunk_index=1, content="ijklmnopqr", start_offset=8, end_offset=18)
    assert chunks[2] == TextChunk(chunk_index=2, content="qrstuvwxyz", start_offset=16, end_offset=26)


def test_chunk_text_chars_empty():
    assert chunk_text_chars("") == []
