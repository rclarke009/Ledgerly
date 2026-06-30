"""Tests for ask trace context isolation."""

import logging

from app.ask_trace import AskTraceContext, ask_trace_scope, log_ask_event


def test_log_ask_event_no_op_without_scope(caplog):
    log_ask_event("orphan", foo=1)
    assert "ask_trace" not in caplog.text


def test_log_ask_event_with_scope(caplog):
    ctx = AskTraceContext(request_id="r1", http_route="POST /ask", question_preview="hi")
    with caplog.at_level(logging.INFO):
        with ask_trace_scope(ctx):
            log_ask_event("ask_begin", top_k=5)
    assert "ask_begin" in caplog.text
