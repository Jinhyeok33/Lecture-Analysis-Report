"""Structured logging helpers for the LLM engine namespace."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import uuid
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "llm_trace_id",
    default=None,
)


def set_trace_id(trace_id: str | None = None) -> str:
    value = trace_id or uuid.uuid4().hex[:12]
    _trace_id_var.set(value)
    return value


def get_trace_id() -> str | None:
    return _trace_id_var.get()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=KST).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        trace_id = _trace_id_var.get()
        if trace_id is not None:
            payload["trace_id"] = trace_id
        if record.exc_info and record.exc_info[1]:
            payload["exception"] = self.formatException(record.exc_info)
        for key in ("lecture_id", "chunk_id", "stage"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


class ReadableFormatter(logging.Formatter):
    FMT = "%(asctime)s [%(levelname)-5s] %(name)s - %(message)s"
    DATEFMT = "%H:%M:%S"

    def __init__(self) -> None:
        super().__init__(fmt=self.FMT, datefmt=self.DATEFMT)

    def format(self, record: logging.LogRecord) -> str:
        trace_id = _trace_id_var.get()
        if trace_id is not None:
            record.msg = f"[{trace_id}] {record.msg}"
        return super().format(record)


def setup_logging(level: str | int = "INFO", json_format: bool = False) -> None:
    root_logger = logging.getLogger("src.llm_engine")
    if root_logger.handlers:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if json_format else ReadableFormatter())
    root_logger.setLevel(level)
    root_logger.addHandler(handler)
    root_logger.propagate = False
