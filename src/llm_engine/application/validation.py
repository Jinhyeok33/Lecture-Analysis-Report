"""Evidence 검증 전용 모듈."""

from __future__ import annotations

import logging
import re
from typing import List

from src.llm_engine.core.schemas import Evidence

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    from difflib import SequenceMatcher
    logger.warning("rapidfuzz 라이브러리가 없습니다. 성능 저하를 유발하는 difflib을 사용합니다. (pip install rapidfuzz 권장)")

DEFAULT_SIMILARITY_THRESHOLD = 0.80

def normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[\s\W]+", "", text)

def validate_evidence_quote(
    quote: str,
    chunk_text: str,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> bool:
    if not quote.strip():
        return False

    n_quote = normalize_text(quote)
    n_chunk = normalize_text(chunk_text)

    if not n_quote:
        return False

    if n_quote in n_chunk:
        return True

    if HAS_RAPIDFUZZ:
        score = fuzz.partial_ratio(n_quote, n_chunk)
        return score >= (similarity_threshold * 100)
    else:
        return SequenceMatcher(None, n_quote, n_chunk).ratio() >= similarity_threshold

HALLUCINATION_MIN_PASS_RATIO = 0.5
HALLUCINATION_MAX_EFFECTIVE_REQUEST = 6

def validate_evidence(
    evidence_list: List[Evidence],
    chunk_text: str,
    min_pass_ratio: float = HALLUCINATION_MIN_PASS_RATIO,
    max_effective_request: int = HALLUCINATION_MAX_EFFECTIVE_REQUEST,
) -> List[Evidence]:
    if not evidence_list:
        return []

    passed = [e for e in evidence_list if validate_evidence_quote(e.quote, chunk_text)]
    requested = len(evidence_list)

    if requested > 0:
        effective_requested = min(requested, max_effective_request)
        pass_ratio = len(passed) / effective_requested

        if len(passed) == 0 or pass_ratio < min_pass_ratio:
            raise ValueError(
                "환각 감지: 원문에서 찾을 수 없는 인용이 많습니다 "
                f"(통과={len(passed)}, 요청={requested}, 판정요청={effective_requested}). "
                "인용 추출을 더 엄격히 한 뒤 재시도하세요."
            )

    return passed
