"""LLMEngine 구조화 로깅 설정.

한 번 `setup_logging()`을 호출하면 LLMEngine 네임스페이스 전체에
JSON 구조화 포맷 또는 사람 친화적 텍스트 포맷이 적용된다.

사용법:
    from LLMEngine.core.logging_config import setup_logging
    setup_logging()                    # 기본: 텍스트 포맷, INFO
    setup_logging(json_format=True)    # 운영: JSON 포맷
    setup_logging(level="DEBUG")       # 디버그 모드

trace_id:
    from LLMEngine.core.logging_config import set_trace_id, get_trace_id
    set_trace_id("my-request-id")     # 요청 단위 추적 ID 설정
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import uuid
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "llm_trace_id", default=None,
)


def set_trace_id(trace_id: str | None = None) -> str:
    """현재 컨텍스트에 trace_id를 설정한다. None이면 UUID4 자동 생성."""
    tid = trace_id or uuid.uuid4().hex[:12]
    _trace_id_var.set(tid)
    return tid


def get_trace_id() -> str | None:
    """현재 컨텍스트의 trace_id를 반환한다."""
    return _trace_id_var.get()


class JsonFormatter(logging.Formatter):
    """로그 레코드를 JSON 한 줄로 직렬화한다."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=KST).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        tid = _trace_id_var.get()
        if tid is not None:
            log_entry["trace_id"] = tid
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        for key in ("lecture_id", "chunk_id", "stage"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val
        return json.dumps(log_entry, ensure_ascii=False)


class ReadableFormatter(logging.Formatter):
    """개발 환경용 사람 친화적 포맷."""

    FMT = "%(asctime)s [%(levelname)-5s] %(name)s — %(message)s"
    DATEFMT = "%H:%M:%S"

    def __init__(self) -> None:
        super().__init__(fmt=self.FMT, datefmt=self.DATEFMT)

    def format(self, record: logging.LogRecord) -> str:
        tid = _trace_id_var.get()
        if tid is not None:
            record.msg = f"[{tid}] {record.msg}"
        return super().format(record)


def setup_logging(
    level: str | int = "INFO",
    json_format: bool = False,
) -> None:
    """LLMEngine 네임스페이스 로거를 초기화한다.

    Args:
        level: 로그 레벨 (기본 INFO).
        json_format: True면 JSON 포맷, False면 사람 친화적 텍스트 포맷.
    """
    root_logger = logging.getLogger("LLMEngine")

    if root_logger.handlers:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if json_format else ReadableFormatter())

    root_logger.setLevel(level)
    root_logger.addHandler(handler)
    root_logger.propagate = False
