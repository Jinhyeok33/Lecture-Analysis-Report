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

try:
    from rapidfuzz import fuzz as _rfuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False
    from difflib import SequenceMatcher as _SequenceMatcher

from LLMEngine.core.ports import (
    ILLMProvider, EvidenceValidationDetail,
    EvidenceValidator, AggregatorPromptBuilder,
)
from LLMEngine.core.schemas import (
    ChunkMetadata, ChunkResult, ChunkScores, ChunkStatus, Evidence,
    LLMInternalResponse, ReliabilityMetrics, RefinedList, TokenUsage,
    NA_CAPABLE_ITEMS,
)
from LLMEngine.core.exceptions import (
    RefusalError, HallucinationError, LanguageViolationError,
    CotMismatchError, TruncatedResponseError, NonRetryableAPIError,
)
from LLMEngine.core.metrics import get_metrics

logger = logging.getLogger(__name__)

AGGREGATOR_MAX_ITEMS = 200
TARGET_SUMMARY_COUNT = 10

_ENGLISH_SENTENCE_RE = re.compile(r"[A-Za-z]{4,}(?:\s+[A-Za-z]{3,}){3,}")


def _contains_english_sentences(text: str) -> bool:
    """reason/issues/strengths에 영어 문장이 4단어 이상 연속으로 포함되면 True."""
    return bool(_ENGLISH_SENTENCE_RE.search(text))


def _flatten_scores(scores: ChunkScores) -> dict[str, int | None]:
    """ChunkScores를 {item: score} flat dict로 변환한다."""
    flat: dict[str, int | None] = {}
    for cat in scores.model_dump().values():
        if isinstance(cat, dict):
            flat.update(cat)
    return flat


def _default_evidence_validator() -> EvidenceValidator:
    from LLMEngine.application.validation import validate_evidence
    return validate_evidence


def _default_prompt_builder() -> AggregatorPromptBuilder:
    from LLMEngine.application.prompts import build_aggregator_refine_prompt
    return build_aggregator_refine_prompt


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
        temperature: float = 1.0,
        seed: int | None = None,
        evidence_validator: EvidenceValidator | None = None,
        aggregator_prompt_builder: AggregatorPromptBuilder | None = None,
    ) -> None:
        self.model = model
        self.dedup_model = dedup_model
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.api_timeout_s = api_timeout_s
        self.temperature = temperature
        self.seed = seed
        self._validate_evidence = evidence_validator or _default_evidence_validator()
        self._build_aggregator_prompt = aggregator_prompt_builder or _default_prompt_builder()

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

    async def __aenter__(self) -> BaseLLMAdapter:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ── Public API ───────────────────────────────────────────────────

    @staticmethod
    def _compute_reliability(
        detail: EvidenceValidationDetail,
        scores: ChunkScores,
        hallucination_retries: int,
    ) -> ReliabilityMetrics:
        evidence_items = {e.item for e in detail.passed}
        flat = _flatten_scores(scores)
        scored = [(item, val) for item, val in flat.items() if val is not None]
        scored_items = len(scored)
        matched = sum(1 for item, _ in scored if item in evidence_items)
        consistency = matched / scored_items if scored_items > 0 else 1.0

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
        score_map = _flatten_scores(p.scores)
        cleaned_evidence = [
            e for e in detail.passed
            if score_map.get(e.item) is not None and score_map[e.item] != 3
        ]

        return ChunkResult(
            chunk_id=chunk_data.chunk_id,
            start_time=chunk_data.start_time, end_time=chunk_data.end_time,
            scores=p.scores, strengths=p.strengths, issues=p.issues,
            evidence=cleaned_evidence, status=ChunkStatus.SUCCESS, is_fallback=False,
            retry_count=retry_count, token_usage=usage,
            reliability=reliability,
        )

    def analyze_chunk(self, chunk_data: ChunkMetadata) -> ChunkResult:
        t0 = time.perf_counter()
        parsed, retry_count, usage, detail, h_retries = self._request_structured(chunk_data)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        reliability = self._compute_reliability(detail, parsed.final_output.scores, h_retries)
        result = self._build_success_result(chunk_data, parsed, detail, retry_count, usage, reliability)
        result.elapsed_ms = elapsed_ms
        return result

    async def analyze_chunk_async(self, chunk_data: ChunkMetadata) -> ChunkResult:
        t0 = time.perf_counter()
        parsed, retry_count, usage, detail, h_retries = await self._request_structured_async(chunk_data)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        reliability = self._compute_reliability(detail, parsed.final_output.scores, h_retries)
        result = self._build_success_result(chunk_data, parsed, detail, retry_count, usage, reliability)
        result.elapsed_ms = elapsed_ms
        return result

    def aggregate_results(
        self, items: List[str], label: str, scores_context: str, trends: str,
        max_aggregate_retries: int = 3,
    ) -> Tuple[List[str], TokenUsage]:
        user_content = self._build_aggregator_prompt(
            items[:AGGREGATOR_MAX_ITEMS], label, scores_context, trends,
        )
        last_error: Exception | None = None
        for attempt in range(1, max_aggregate_retries + 1):
            try:
                response = self._call_aggregate_sync(user_content)
                result_items = self._parse_aggregate_response(response).items
                usage = self._build_single_usage(response)
                return self._normalize_count(result_items, items), usage
            except (RefusalError, NonRetryableAPIError) as e:
                logger.error("LLM 통합 요약 복구 불가 오류 (%s): %s", type(e).__name__, e)
                raise
            except Exception as e:
                last_error = e
                logger.warning(
                    "LLM 통합 요약 attempt=%d/%d 실패 (%s): %s",
                    attempt, max_aggregate_retries, type(e).__name__, e,
                )
                if attempt < max_aggregate_retries:
                    time.sleep(self._backoff(attempt))

        logger.warning("LLM 통합 요약 %d회 시도 후 실패; 어휘 기반 중복 제거로 대체. 마지막 오류: %s",
                       max_aggregate_retries, last_error)
        return self._normalize_count([], items), TokenUsage()

    # ── Validation (공통) ────────────────────────────────────────────

    @staticmethod
    def _check_language(parsed: LLMInternalResponse) -> None:
        """응답에 영어 문장이 섞여 있으면 LanguageViolationError를 raise한다."""
        p = parsed.final_output
        texts = [
            *(p.strengths or []),
            *(p.issues or []),
            *(ev.reason for ev in (p.evidence or [])),
            *(cot.anchor for cot in parsed.cot),
        ]
        for t in texts:
            if _contains_english_sentences(t):
                raise LanguageViolationError(
                    f"언어 위반 감지: 응답에 영어 문장 혼입 — '{t[:80]}...'"
                )

    @staticmethod
    def _validate_cot_consistency(parsed: LLMInternalResponse) -> None:
        """CoT 점수와 final_output 점수의 정합성을 검증한다."""
        cot_scores = {ev.item: ev.score for ev in parsed.cot}
        final_flat = _flatten_scores(parsed.final_output.scores)

        mismatches = [
            f"{item}: CoT={cot_val} ≠ output={final_flat.get(item)}"
            for item, cot_val in cot_scores.items()
            if not (cot_val is None and final_flat.get(item) is None)
            and cot_val != final_flat.get(item)
        ]
        if mismatches:
            raise CotMismatchError(
                f"CoT 정합성 위반 감지 ({len(mismatches)}건): "
                + "; ".join(mismatches[:5])
            )

    def _validate_parsed(
        self, response: Any, chunk_data: ChunkMetadata,
    ) -> Tuple[LLMInternalResponse, EvidenceValidationDetail]:
        """파싱 → 언어 → CoT → evidence 검증을 순차 수행한다."""
        parsed = self._parse_structured_response(response)
        self._check_language(parsed)
        self._validate_cot_consistency(parsed)
        detail = self._validate_evidence(parsed.final_output.evidence, chunk_data.text)
        return parsed, detail

    # ── Retry error handling (공통) ───────────────────────────────────

    def _handle_retry_error(
        self, exc: Exception, chunk_id: int, attempt: int,
    ) -> None:
        """재시도 불가 예외는 즉시 raise, 그 외는 로깅만 수행한다.

        Raises:
            NonRetryableAPIError: TruncatedResponseError 또는 _should_not_retry 판정 시
            RuntimeError: RefusalError wrapping
        """
        if isinstance(exc, RefusalError):
            logger.error("chunk_id=%02d attempt=%d refusal: %s", chunk_id, attempt, exc)
            raise RuntimeError(f"재시도 불가 — 모델 거부: {exc}") from exc

        if isinstance(exc, TruncatedResponseError):
            logger.error("chunk_id=%02d attempt=%d 응답 잘림: %s", chunk_id, attempt, exc)
            raise NonRetryableAPIError(f"재시도 불가 — 응답 잘림: {exc}") from exc

        if isinstance(exc, HallucinationError):
            logger.warning("chunk_id=%02d attempt=%d 환각 감지: %s", chunk_id, attempt, exc)
            return

        if isinstance(exc, (LanguageViolationError, CotMismatchError, TimeoutError)):
            label = "TimeoutError (%.1fs)" % self.api_timeout_s if isinstance(exc, TimeoutError) else type(exc).__name__
            logger.warning("chunk_id=%02d attempt=%d %s: %s", chunk_id, attempt, label, exc)
            return

        if self._should_not_retry(exc):
            logger.error("chunk_id=%02d attempt=%d %s retryable=False: %s",
                         chunk_id, attempt, type(exc).__name__, exc)
            raise NonRetryableAPIError(f"재시도 불가 오류: {exc}") from exc

        logger.warning("chunk_id=%02d attempt=%d %s: %s",
                       chunk_id, attempt, type(exc).__name__, exc)

    # ── Sync retry loop ──────────────────────────────────────────────

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
                parsed, detail = self._validate_parsed(response, chunk_data)
                return parsed, attempt - 1, accumulated, detail, hallucination_retries
            except Exception as exc:
                if isinstance(exc, HallucinationError):
                    hallucination_retries += 1
                self._handle_retry_error(exc, chunk_data.chunk_id, attempt)
                last_error = exc
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
                parsed, detail = self._validate_parsed(response, chunk_data)
                return parsed, attempt - 1, accumulated, detail, hallucination_retries
            except asyncio.CancelledError:
                logger.warning("chunk_id=%02d attempt=%d CancelledError — 재전파",
                               chunk_data.chunk_id, attempt)
                raise
            except Exception as exc:
                if isinstance(exc, HallucinationError):
                    hallucination_retries += 1
                self._handle_retry_error(exc, chunk_data.chunk_id, attempt)
                last_error = exc
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
        metrics = get_metrics()
        metrics.observe("llm_call_duration_s", elapsed_s, chunk_id=str(chunk_id))
        metrics.observe("llm_call_cost_usd", float(cost), model=self.model)
        metrics.increment("llm_call_total", model=self.model)
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
            if _HAS_RAPIDFUZZ:
                is_dup = any(_rfuzz.ratio(candidate, e) >= threshold_100 for e in result)
            else:
                is_dup = any(
                    _SequenceMatcher(None, candidate, e).ratio() * 100 >= threshold_100
                    for e in result
                )
            if is_dup:
                continue
            result.append(candidate)
        return result
