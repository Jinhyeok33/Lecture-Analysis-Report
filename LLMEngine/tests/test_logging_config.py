"""logging_config.py 단위 테스트 — JSON / Readable 포맷, trace_id, 중복 초기화 방지."""

from __future__ import annotations

import json
import logging

import pytest

from LLMEngine.core.logging_config import (
    JsonFormatter, ReadableFormatter, setup_logging,
    set_trace_id, get_trace_id, _trace_id_var,
)


@pytest.fixture(autouse=True)
def _reset_logger():
    """각 테스트 후 LLMEngine 로거 핸들러를 정리하고 trace_id를 초기화한다."""
    yield
    llm_logger = logging.getLogger("LLMEngine")
    llm_logger.handlers.clear()
    _trace_id_var.set(None)


class TestJsonFormatter:
    def test_output_is_valid_json(self):
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="LLMEngine.test", level=logging.INFO, pathname="", lineno=0,
            msg="테스트 메시지", args=(), exc_info=None,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["msg"] == "테스트 메시지"
        assert "ts" in parsed

    def test_extra_fields(self):
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="LLMEngine.test", level=logging.WARNING, pathname="", lineno=0,
            msg="chunk error", args=(), exc_info=None,
        )
        record.lecture_id = "lec01"
        record.chunk_id = 3
        record.stage = "analyze"
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["lecture_id"] == "lec01"
        assert parsed["chunk_id"] == 3
        assert parsed["stage"] == "analyze"


class TestReadableFormatter:
    def test_output_contains_level(self):
        fmt = ReadableFormatter()
        record = logging.LogRecord(
            name="LLMEngine.test", level=logging.ERROR, pathname="", lineno=0,
            msg="에러 발생", args=(), exc_info=None,
        )
        output = fmt.format(record)
        assert "ERROR" in output
        assert "에러 발생" in output


class TestSetupLogging:
    def test_json_mode(self):
        setup_logging(json_format=True)
        llm_logger = logging.getLogger("LLMEngine")
        assert len(llm_logger.handlers) == 1
        assert isinstance(llm_logger.handlers[0].formatter, JsonFormatter)

    def test_text_mode(self):
        setup_logging(json_format=False)
        llm_logger = logging.getLogger("LLMEngine")
        assert len(llm_logger.handlers) == 1
        assert isinstance(llm_logger.handlers[0].formatter, ReadableFormatter)

    def test_no_duplicate_handlers(self):
        setup_logging()
        setup_logging()
        llm_logger = logging.getLogger("LLMEngine")
        assert len(llm_logger.handlers) == 1


class TestTraceId:
    def test_set_and_get(self):
        tid = set_trace_id("test-123")
        assert tid == "test-123"
        assert get_trace_id() == "test-123"

    def test_auto_generate(self):
        tid = set_trace_id()
        assert tid is not None
        assert len(tid) == 12
        assert get_trace_id() == tid

    def test_default_none(self):
        assert get_trace_id() is None

    def test_json_formatter_includes_trace_id(self):
        set_trace_id("trace-abc")
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="LLMEngine.test", level=logging.INFO, pathname="", lineno=0,
            msg="traced message", args=(), exc_info=None,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["trace_id"] == "trace-abc"

    def test_json_formatter_no_trace_id_when_unset(self):
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="LLMEngine.test", level=logging.INFO, pathname="", lineno=0,
            msg="no trace", args=(), exc_info=None,
        )
        output = fmt.format(record)
        parsed = json.loads(output)
        assert "trace_id" not in parsed

    def test_readable_formatter_includes_trace_id(self):
        set_trace_id("trace-xyz")
        fmt = ReadableFormatter()
        record = logging.LogRecord(
            name="LLMEngine.test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        output = fmt.format(record)
        assert "[trace-xyz]" in output
