"""Evidence 검증 전용 모듈."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List

from LLMEngine.core.schemas import Evidence

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    from difflib import SequenceMatcher
    logger.warning("rapidfuzz 미설치 — difflib fallback 사용 (pip install rapidfuzz 권장)")

# 임계값 조정 가이드:
#   0.90+  : 엄격. false negative 증가, 재시도 비용 상승.
#   0.80   : 조사·띄어쓰기 변형 허용. 현재 권장값.
#   0.70-  : 느슨. 환각 통과 위험.
DEFAULT_SIMILARITY_THRESHOLD = 0.80

HALLUCINATION_MIN_PASS_RATIO = 0.5
HALLUCINATION_MAX_EFFECTIVE_REQUEST = 6


@dataclass
class EvidenceValidationDetail:
    """validate_evidence 반환 객체. 신뢰도 산출에 필요한 세부 지표를 포함."""
    passed: List[Evidence]
    total_requested: int = 0
    total_passed: int = 0
    pass_ratio: float = 1.0
    similarity_scores: List[float] = field(default_factory=list)
    avg_similarity: float = 100.0


def normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[\s\W]+", "", text)


def _compute_similarity(quote: str, chunk_text: str) -> float:
    """quote와 chunk_text 간 유사도를 0-100 스케일로 반환."""
    n_quote = normalize_text(quote)
    n_chunk = normalize_text(chunk_text)

    if not n_quote:
        return 0.0
    if n_quote in n_chunk:
        return 100.0

    if HAS_RAPIDFUZZ:
        return float(fuzz.partial_ratio(n_quote, n_chunk))

    q_len = len(n_quote)
    if q_len > len(n_chunk):
        return SequenceMatcher(None, n_quote, n_chunk).ratio() * 100
    step = max(1, q_len // 4)
    best = 0.0
    for i in range(0, len(n_chunk) - q_len + 1, step):
        ratio = SequenceMatcher(None, n_quote, n_chunk[i:i + q_len]).ratio() * 100
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
        return EvidenceValidationDetail(passed=[])

    threshold_100 = DEFAULT_SIMILARITY_THRESHOLD * 100
    passed: List[Evidence] = []
    sim_scores: List[float] = []

    for ev in evidence_list:
        score = _compute_similarity(ev.quote, chunk_text)
        if score >= threshold_100:
            passed.append(ev)
            sim_scores.append(score)

    requested = len(evidence_list)
    effective_requested = min(requested, max_effective_request)
    raw_ratio = len(passed) / effective_requested if effective_requested > 0 else 1.0
    pass_ratio = min(raw_ratio, 1.0)

    if len(passed) == 0 or raw_ratio < min_pass_ratio:
        raise ValueError(
            "환각 감지: 원문에서 찾을 수 없는 인용이 많습니다 "
            f"(통과={len(passed)}, 요청={requested}, 판정요청={effective_requested}). "
            "인용 추출을 더 엄격히 한 뒤 재시도하세요."
        )

    avg_sim = sum(sim_scores) / len(sim_scores) if sim_scores else 0.0

    return EvidenceValidationDetail(
        passed=passed,
        total_requested=requested,
        total_passed=len(passed),
        pass_ratio=round(pass_ratio, 4),
        similarity_scores=sim_scores,
        avg_similarity=round(avg_sim, 2),
    )
