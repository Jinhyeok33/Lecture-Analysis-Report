"""Evidence 검증 전용 모듈."""

from __future__ import annotations

import logging
import re
from typing import List

from src.llm_engine.core.exceptions import HallucinationError
from src.llm_engine.core.ports import EvidenceValidationDetail
from src.llm_engine.core.schemas import Evidence

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz

    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    from difflib import SequenceMatcher

    logger.warning("rapidfuzz 미설치 — difflib fallback 사용 (pip install rapidfuzz 권장)")

DEFAULT_SIMILARITY_THRESHOLD = 0.80

HALLUCINATION_MIN_PASS_RATIO = 0.5
HALLUCINATION_MAX_EFFECTIVE_REQUEST = 6


def normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[\s\W]+", "", text)


def _compute_similarity(quote: str, chunk_text: str) -> float:
    n_quote = normalize_text(quote)
    n_chunk = normalize_text(chunk_text)

    if not n_quote:
        return 0.0
    if n_quote in n_chunk:
        return 100.0

    if HAS_RAPIDFUZZ:
        return float(fuzz.partial_ratio(n_quote, n_chunk))

    quote_length = len(n_quote)
    if quote_length > len(n_chunk):
        return SequenceMatcher(None, n_quote, n_chunk).ratio() * 100

    step = max(1, quote_length // 4)
    best = 0.0
    for index in range(0, len(n_chunk) - quote_length + 1, step):
        ratio = SequenceMatcher(None, n_quote, n_chunk[index : index + quote_length]).ratio() * 100
        if ratio > best:
            best = ratio
    return best


def validate_evidence_quote(
    quote: str,
    chunk_text: str,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> bool:
    if not quote.strip():
        return False
    score = _compute_similarity(quote, chunk_text)
    return score >= (similarity_threshold * 100)


def validate_evidence(
    evidence_list: List[Evidence],
    chunk_text: str,
    min_pass_ratio: float = HALLUCINATION_MIN_PASS_RATIO,
    max_effective_request: int = HALLUCINATION_MAX_EFFECTIVE_REQUEST,
) -> EvidenceValidationDetail:
    if not evidence_list:
        return EvidenceValidationDetail(
            passed=[],
            total_requested=0,
            total_passed=0,
            pass_ratio=0.0,
            similarity_scores=[],
            avg_similarity=0.0,
        )

    threshold_100 = DEFAULT_SIMILARITY_THRESHOLD * 100
    passed: List[Evidence] = []
    similarity_scores: List[float] = []

    for evidence in evidence_list:
        score = _compute_similarity(evidence.quote, chunk_text)
        if score >= threshold_100:
            passed.append(evidence)
            similarity_scores.append(score)

    requested = len(evidence_list)
    effective_requested = min(requested, max_effective_request)
    raw_ratio = len(passed) / effective_requested if effective_requested > 0 else 1.0
    pass_ratio = min(raw_ratio, 1.0)

    if len(passed) == 0 or raw_ratio < min_pass_ratio:
        raise HallucinationError(
            "환각 감지: 원문에서 찾을 수 없는 인용이 많습니다 "
            f"(통과={len(passed)}, 요청={requested}, 판정요청={effective_requested}). "
            "인용 추출을 더 엄격히 한 뒤 재시도하세요.",
        )

    avg_similarity = sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0.0
    return EvidenceValidationDetail(
        passed=passed,
        total_requested=requested,
        total_passed=len(passed),
        pass_ratio=round(pass_ratio, 4),
        similarity_scores=similarity_scores,
        avg_similarity=round(avg_similarity, 2),
    )
