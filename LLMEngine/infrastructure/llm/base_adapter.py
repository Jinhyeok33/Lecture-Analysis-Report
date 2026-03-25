"""LLM 어댑터 공통 로직: 재시도, 검증, 집계."""

from __future__ import annotations

import abc
import asyncio
import logging
import random
import re
import time
from collections import Counter
from decimal import Decimal
from typing import Any, List, Tuple

from rapidfuzz import fuzz as _rfuzz

from LLMEngine.core.ports import ILLMProvider
from LLMEngine.core.schemas import (
    ChunkMetadata, ChunkResult, ChunkScores, ChunkStatus, Evidence,
    LLMInternalResponse, ReliabilityMetrics, RefinedList, TokenUsage,
)
from LLMEngine.application.prompts import build_aggregator_refine_prompt
from LLMEngine.application.validation import EvidenceValidationDetail, validate_evidence

logger = logging.getLogger(__name__)

AGGREGATOR_MAX_ITEMS = 200
TARGET_SUMMARY_COUNT = 10

_ENGLISH_SENTENCE_RE = re.compile(r"[A-Za-z]{4,}(?:\s+[A-Za-z]{3,}){3,}")


def _contains_english_sentences(text: str) -> bool:
    """reason/issues/strengths에 영어 문장이 4단어 이상 연속으로 포함되면 True."""
    return bool(_ENGLISH_SENTENCE_RE.search(text))


class RefusalError(RuntimeError):
    """모델이 요청을 거부 — 재시도 불가, 입력/프롬프트 수정 필요."""


class BaseLLMAdapter(ILLMProvider, abc.ABC):
    similarity_threshold = 0.82

    def __init__(
        self,
        *,
        model: str,
        dedup_model: str,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        api_timeout_s: float = 120.0,
    ) -> None:
        self.model = model
        self.dedup_model = dedup_model
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.api_timeout_s = api_timeout_s

    @property
    def model_name(self) -> str:
        return self.model

    # ── Subclass hooks ───────────────────────────────────────────────

    @abc.abstractmethod
    def _call_chunk_sync(self, chunk_data: ChunkMetadata) -> Any: ...

    @abc.abstractmethod
    async def _call_chunk_async(self, chunk_data: ChunkMetadata) -> Any: ...

    @abc.abstractmethod
    def _parse_structured_response(self, response: Any) -> LLMInternalResponse: ...

    @abc.abstractmethod
    def _extract_usage(self, response: Any) -> Tuple[int, int, int]:
        """Return (prompt_tokens, completion_tokens, total_tokens)."""

    @abc.abstractmethod
    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal: ...

    @abc.abstractmethod
    def _should_not_retry(self, exc: Exception) -> bool: ...

    @abc.abstractmethod
    def _call_aggregate_sync(self, user_content: str) -> Any: ...

    @abc.abstractmethod
    def _parse_aggregate_response(self, response: Any) -> RefinedList: ...

    async def close(self) -> None:
        """비동기 리소스 해제. 필요 시 서브클래스에서 오버라이드."""

    # ── Public API ───────────────────────────────────────────────────

    @staticmethod
    def _compute_reliability(
        detail: EvidenceValidationDetail,
        scores: ChunkScores,
        hallucination_retries: int,
    ) -> ReliabilityMetrics:
        evidence_items = {e.item for e in detail.passed}
        non_default = 0
        matched = 0
        for cat_scores in scores.model_dump().values():
            if not isinstance(cat_scores, dict):
                continue
            for item, val in cat_scores.items():
                if val is None or val == 3:
                    continue
                non_default += 1
                if item in evidence_items:
                    matched += 1
        consistency = matched / non_default if non_default > 0 else 1.0

        overall = (
            0.35 * detail.pass_ratio
            + 0.25 * (1.0 - min(hallucination_retries / 3.0, 1.0))
            + 0.20 * (detail.avg_similarity / 100.0)
            + 0.20 * consistency
        )
        return ReliabilityMetrics(
            evidence_pass_ratio=round(detail.pass_ratio, 4),
            hallucination_retries=hallucination_retries,
            avg_evidence_similarity=round(detail.avg_similarity, 2),
            score_evidence_consistency=round(consistency, 4),
            overall_reliability_score=round(min(overall, 1.0), 4),
        )

    @staticmethod
    def _build_success_result(
        chunk_data: ChunkMetadata,
        parsed: LLMInternalResponse,
        detail: EvidenceValidationDetail,
        retry_count: int,
        usage: TokenUsage,
        reliability: ReliabilityMetrics,
    ) -> ChunkResult:
        p = parsed.final_output
        return ChunkResult(
            chunk_id=chunk_data.chunk_id,
            start_time=chunk_data.start_time, end_time=chunk_data.end_time,
            scores=p.scores, strengths=p.strengths, issues=p.issues,
            evidence=detail.passed, status=ChunkStatus.SUCCESS, is_fallback=False,
            retry_count=retry_count, token_usage=usage,
            reliability=reliability,
        )

    def analyze_chunk(self, chunk_data: ChunkMetadata) -> ChunkResult:
        parsed, retry_count, usage, detail, h_retries = self._request_structured(chunk_data)
        reliability = self._compute_reliability(detail, parsed.final_output.scores, h_retries)
        return self._build_success_result(chunk_data, parsed, detail, retry_count, usage, reliability)

    async def analyze_chunk_async(self, chunk_data: ChunkMetadata) -> ChunkResult:
        parsed, retry_count, usage, detail, h_retries = await self._request_structured_async(chunk_data)
        reliability = self._compute_reliability(detail, parsed.final_output.scores, h_retries)
        return self._build_success_result(chunk_data, parsed, detail, retry_count, usage, reliability)

    def aggregate_results(
        self, items: List[str], label: str, scores_context: str, trends: str,
    ) -> Tuple[List[str], TokenUsage]:
        user_content = build_aggregator_refine_prompt(
            items[:AGGREGATOR_MAX_ITEMS], label, scores_context, trends,
        )
        try:
            response = self._call_aggregate_sync(user_content)
            result_items = self._parse_aggregate_response(response).items
            usage = self._build_single_usage(response)
        except Exception as e:
            logger.warning("LLM 통합 요약 실패 (%s); 어휘 기반 중복 제거로 대체.", e)
            return self._normalize_count([], items), TokenUsage()

        return self._normalize_count(result_items, items), usage

    # ── Sync retry loop ──────────────────────────────────────────────

    @staticmethod
    def _check_language(parsed: LLMInternalResponse) -> None:
        """응답에 영어 문장이 섞여 있으면 ValueError를 발생시켜 재시도한다."""
        texts_to_check: list[str] = []
        p = parsed.final_output
        texts_to_check.extend(p.strengths or [])
        texts_to_check.extend(p.issues or [])
        for ev in (p.evidence or []):
            texts_to_check.append(ev.reason)
        for t in texts_to_check:
            if _contains_english_sentences(t):
                raise ValueError(
                    f"언어 위반 감지: 응답에 영어 문장 혼입 — '{t[:80]}...'"
                )

    def _request_structured(
        self, chunk_data: ChunkMetadata,
    ) -> Tuple[LLMInternalResponse, int, TokenUsage, EvidenceValidationDetail, int]:
        last_error: Exception | None = None
        accumulated = TokenUsage()
        hallucination_retries = 0

        for attempt in range(1, self.max_retries + 1):
            try:
                t0 = time.perf_counter()
                response = self._call_chunk_sync(chunk_data)
                elapsed = time.perf_counter() - t0
                accumulated = self._accum(accumulated, response, elapsed, chunk_data.chunk_id, attempt)
                parsed = self._parse_structured_response(response)
                self._check_language(parsed)
                detail = validate_evidence(parsed.final_output.evidence, chunk_data.text)
                return parsed, attempt - 1, accumulated, detail, hallucination_retries

            except RefusalError as exc:
                logger.error("chunk_id=%02d attempt=%d refusal: %s", chunk_data.chunk_id, attempt, exc)
                raise RuntimeError(f"재시도 불가 — 모델 거부: {exc}") from exc

            except ValueError as exc:
                msg = str(exc)
                retryable = "환각 감지" in msg or "언어 위반 감지" in msg
                if not retryable:
                    raise
                if "환각 감지" in msg:
                    hallucination_retries += 1
                last_error = exc
                logger.warning("chunk_id=%02d attempt=%d 검증 실패 (h_retry=%d): %s",
                               chunk_data.chunk_id, attempt, hallucination_retries, exc)
                if attempt < self.max_retries:
                    time.sleep(self._backoff(attempt))

            except Exception as exc:
                last_error = exc
                if self._should_not_retry(exc):
                    logger.error("chunk_id=%02d attempt=%d %s retryable=False: %s",
                                 chunk_data.chunk_id, attempt, type(exc).__name__, exc)
                    raise RuntimeError(f"재시도 불가 오류: {exc}") from exc
                logger.warning("chunk_id=%02d attempt=%d %s: %s",
                               chunk_data.chunk_id, attempt, type(exc).__name__, exc)
                if attempt < self.max_retries:
                    time.sleep(self._backoff(attempt))

        raise RuntimeError(f"{self.max_retries}회 시도 후 실패: {last_error}") from last_error

    # ── Async retry loop ─────────────────────────────────────────────

    async def _request_structured_async(
        self, chunk_data: ChunkMetadata,
    ) -> Tuple[LLMInternalResponse, int, TokenUsage, EvidenceValidationDetail, int]:
        last_error: Exception | None = None
        accumulated = TokenUsage()
        hallucination_retries = 0

        for attempt in range(1, self.max_retries + 1):
            try:
                await asyncio.sleep(0.1)
                t0 = asyncio.get_running_loop().time()
                response = await self._call_chunk_async(chunk_data)
                elapsed = asyncio.get_running_loop().time() - t0
                accumulated = self._accum(
                    accumulated, response, elapsed, chunk_data.chunk_id, attempt, is_async=True,
                )
                parsed = self._parse_structured_response(response)
                self._check_language(parsed)
                detail = validate_evidence(parsed.final_output.evidence, chunk_data.text)
                return parsed, attempt - 1, accumulated, detail, hallucination_retries

            except asyncio.CancelledError:
                logger.warning(
                    "chunk_id=%02d attempt=%d CancelledError — 재전파",
                    chunk_data.chunk_id, attempt,
                )
                raise

            except RefusalError as exc:
                logger.error("chunk_id=%02d attempt=%d refusal: %s", chunk_data.chunk_id, attempt, exc)
                raise RuntimeError(f"재시도 불가 — 모델 거부: {exc}") from exc

            except TimeoutError as exc:
                last_error = exc
                logger.warning(
                    "chunk_id=%02d attempt=%d TimeoutError (%.1fs)",
                    chunk_data.chunk_id, attempt, self.api_timeout_s,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(self._backoff(attempt))

            except ValueError as exc:
                msg = str(exc)
                retryable = "환각 감지" in msg or "언어 위반 감지" in msg
                if not retryable:
                    raise
                if "환각 감지" in msg:
                    hallucination_retries += 1
                last_error = exc
                logger.warning("chunk_id=%02d attempt=%d 검증 실패 (h_retry=%d): %s",
                               chunk_data.chunk_id, attempt, hallucination_retries, exc)
                if attempt < self.max_retries:
                    await asyncio.sleep(self._backoff(attempt))

            except Exception as exc:
                last_error = exc
                if self._should_not_retry(exc):
                    logger.error("chunk_id=%02d attempt=%d %s retryable=False: %s",
                                 chunk_data.chunk_id, attempt, type(exc).__name__, exc)
                    raise RuntimeError(f"재시도 불가 오류: {exc}") from exc
                logger.warning("chunk_id=%02d attempt=%d %s: %s",
                               chunk_data.chunk_id, attempt, type(exc).__name__, exc)
                if attempt < self.max_retries:
                    await asyncio.sleep(self._backoff(attempt))

        raise RuntimeError(f"연결 실패 (최대 재시도 초과): {last_error}") from last_error

    # ── Helpers ───────────────────────────────────────────────────────

    def _backoff(self, attempt: int) -> float:
        return self.retry_base_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 1.5)

    def _accum(
        self, accumulated: TokenUsage, response: Any,
        elapsed_s: float, chunk_id: int, attempt: int, is_async: bool = False,
    ) -> TokenUsage:
        pt, ct, tt = self._extract_usage(response)
        if pt == 0 and ct == 0:
            return accumulated
        cost = self._estimate_cost(pt, ct)
        result = accumulated + TokenUsage(
            prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
            estimated_cost_usd=cost, llm_call_count=1,
        )
        logger.info(
            "chunk_id=%02d stage=%s attempt=%d elapsed_ms=%d prompt=%d completion=%d cost=%s",
            chunk_id, "async" if is_async else "sync", attempt,
            int(elapsed_s * 1000), result.prompt_tokens, result.completion_tokens,
            str(result.estimated_cost_usd),
        )
        return result

    def _build_single_usage(self, response: Any) -> TokenUsage:
        pt, ct, tt = self._extract_usage(response)
        if pt == 0 and ct == 0:
            return TokenUsage()
        return TokenUsage(
            prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
            estimated_cost_usd=self._estimate_cost(pt, ct), llm_call_count=1,
        )

    def _normalize_count(self, llm_items: List[str], raw_items: List[str]) -> List[str]:
        """결과를 TARGET_SUMMARY_COUNT개로 정규화 (부족 시 dedup fallback 패딩)."""
        if len(llm_items) >= TARGET_SUMMARY_COUNT:
            return llm_items[:TARGET_SUMMARY_COUNT]
        result = list(llm_items)
        existing = set(result)
        for item in self._deduplicate_ranked(raw_items):
            if item not in existing:
                result.append(item)
                existing.add(item)
            if len(result) >= TARGET_SUMMARY_COUNT:
                break
        return result[:TARGET_SUMMARY_COUNT]

    def _deduplicate_ranked(self, values: List[str]) -> List[str]:
        if not values:
            return ["전체 평가 점수 기반 추가 특이사항 없음."] * TARGET_SUMMARY_COUNT
        counts = Counter(v.strip() for v in values if v.strip())
        ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        threshold_100 = self.similarity_threshold * 100
        result: List[str] = []
        for candidate, _ in ranked:
            if any(_rfuzz.ratio(candidate, e) >= threshold_100 for e in result):
                continue
            result.append(candidate)
        return result
