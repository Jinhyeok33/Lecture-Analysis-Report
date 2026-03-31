"""base_adapter.py 단위 테스트 — mock으로 재시도 루프, 검증 체인, 비용, 중복 제거 검증."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, List, Tuple
from unittest.mock import MagicMock, patch

import pytest

from LLMEngine.core.schemas import (
    ChunkMetadata, ChunkResult, ChunkResultPayload, ChunkScores,
    ConceptClarityScores, Evidence, InteractionScores, ItemEvaluation,
    LLMInternalResponse, LectureStructureScores, PracticeLinkageScores,
    RefinedList, TokenUsage, VALID_ITEMS,
)
from LLMEngine.core.exceptions import (
    RefusalError, HallucinationError, LanguageViolationError,
    CotMismatchError, TruncatedResponseError, NonRetryableAPIError,
)
from LLMEngine.infrastructure.llm.base_adapter import (
    BaseLLMAdapter, _contains_english_sentences, _flatten_scores,
)


def _default_scores() -> ChunkScores:
    return ChunkScores(
        lecture_structure=LectureStructureScores(
            learning_objective_intro=4, previous_lesson_linkage=3,
            explanation_sequence=4, key_point_emphasis=3, closing_summary=4,
        ),
        concept_clarity=ConceptClarityScores(
            concept_definition=4, analogy_example_usage=3, prerequisite_check=3,
        ),
        practice_linkage=PracticeLinkageScores(
            example_appropriateness=3, practice_transition=3, error_handling=3,
        ),
        interaction=InteractionScores(
            participation_induction=3, question_response_sufficiency=3,
        ),
    )


def _default_cot() -> list[ItemEvaluation]:
    scores = _flatten_scores(_default_scores())
    return [
        ItemEvaluation(item=item, quote="인용", anchor="3점: 기본", score=val)
        for item, val in scores.items()
    ]


def _default_parsed() -> LLMInternalResponse:
    return LLMInternalResponse(
        structured_thought_process=_default_cot(),
        final_output=ChunkResultPayload(
            scores=_default_scores(),
            strengths=["학습 목표 명확"],
            issues=["실습 부족"],
            evidence=[Evidence(item="explanation_sequence", quote="테스트 발화입니다", reason="설명 순서 양호")],
        ),
    )


def _make_chunk() -> ChunkMetadata:
    return ChunkMetadata(
        chunk_id=1, start_time="00:00", end_time="00:10",
        text="테스트 발화입니다. 강의 내용을 설명합니다.",
        line_count=2, word_count=5, total_chunks=1,
    )


class StubAdapter(BaseLLMAdapter):
    """테스트용 concrete adapter. hook 메서드만 stub으로 구현."""

    def __init__(self, **kwargs):
        super().__init__(
            model="stub-model", dedup_model="stub-dedup",
            max_retries=kwargs.get("max_retries", 3),
            retry_base_delay=kwargs.get("retry_base_delay", 0.01),
            api_timeout_s=kwargs.get("api_timeout_s", 1.0),
            temperature=kwargs.get("temperature", 0.5),
            seed=kwargs.get("seed", 42),
        )
        self._call_responses: list[Any] = []
        self._call_count = 0
        self._parsed_response = _default_parsed()
        self._should_not_retry_val = False
        self._aggregate_response: Any = None

    def _call_chunk_sync(self, chunk_data: ChunkMetadata) -> Any:
        self._call_count += 1
        if self._call_responses:
            resp = self._call_responses.pop(0)
            if isinstance(resp, Exception):
                raise resp
            return resp
        return MagicMock()

    async def _call_chunk_async(self, chunk_data: ChunkMetadata) -> Any:
        return self._call_chunk_sync(chunk_data)

    def _parse_structured_response(self, response: Any) -> LLMInternalResponse:
        return self._parsed_response

    def _extract_usage(self, response: Any) -> Tuple[int, int, int]:
        return 100, 50, 150

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        return Decimal("0.001")

    def _should_not_retry(self, exc: Exception) -> bool:
        return self._should_not_retry_val

    def _call_aggregate_sync(self, user_content: str) -> Any:
        return self._aggregate_response or MagicMock()

    def _parse_aggregate_response(self, response: Any) -> RefinedList:
        return RefinedList(items=["항목" + str(i) for i in range(10)])


# ── 재시도 루프 테스트 ─────────────────────────────────────────────

class TestRequestStructuredRetry:
    def test_success_first_attempt(self):
        adapter = StubAdapter()
        chunk = _make_chunk()
        parsed, retry_count, usage, detail, h_retries = adapter._request_structured(chunk)
        assert retry_count == 0
        assert h_retries == 0
        assert usage.total_tokens == 150

    def test_hallucination_retry_then_success(self):
        adapter = StubAdapter(max_retries=3)
        chunk = _make_chunk()
        call_count = [0]
        original_validate = adapter._validate_parsed

        def side_effect(response, chunk_data):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise HallucinationError("환각 감지")
            return original_validate(response, chunk_data)

        adapter._validate_parsed = side_effect
        parsed, retry_count, usage, detail, h_retries = adapter._request_structured(chunk)
        assert h_retries == 2
        assert retry_count == 2

    def test_max_retries_exhausted(self):
        adapter = StubAdapter(max_retries=2)
        chunk = _make_chunk()
        adapter._validate_parsed = lambda r, c: (_ for _ in ()).throw(
            LanguageViolationError("영어 혼입")
        )
        with pytest.raises(RuntimeError, match="2회 시도 후 실패"):
            adapter._request_structured(chunk)

    def test_refusal_stops_immediately(self):
        adapter = StubAdapter(max_retries=5)
        chunk = _make_chunk()
        adapter._parse_structured_response = lambda r: (_ for _ in ()).throw(
            RefusalError("거부")
        )
        with pytest.raises(RuntimeError, match="모델 거부"):
            adapter._request_structured(chunk)
        assert adapter._call_count == 1

    def test_truncated_stops_immediately(self):
        adapter = StubAdapter(max_retries=5)
        chunk = _make_chunk()
        adapter._parse_structured_response = lambda r: (_ for _ in ()).throw(
            TruncatedResponseError("잘림")
        )
        with pytest.raises(NonRetryableAPIError, match="응답 잘림"):
            adapter._request_structured(chunk)
        assert adapter._call_count == 1

    def test_non_retryable_api_error(self):
        adapter = StubAdapter(max_retries=5)
        adapter._should_not_retry_val = True
        chunk = _make_chunk()
        adapter._call_responses = [RuntimeError("quota exceeded")]
        with pytest.raises(NonRetryableAPIError):
            adapter._request_structured(chunk)
        assert adapter._call_count == 1


class TestRequestStructuredAsync:
    def test_async_success(self):
        adapter = StubAdapter()
        chunk = _make_chunk()

        async def _run():
            return await adapter._request_structured_async(chunk)

        parsed, retry_count, usage, detail, h_retries = asyncio.run(_run())
        assert retry_count == 0

    def test_async_cancelled_propagated(self):
        adapter = StubAdapter()
        chunk = _make_chunk()

        async def _raising_call(c):
            raise asyncio.CancelledError()

        adapter._call_chunk_async = _raising_call

        async def _run():
            return await adapter._request_structured_async(chunk)

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(_run())


# ── 검증 체인 테스트 ──────────────────────────────────────────────

class TestCheckLanguage:
    def test_korean_only_passes(self):
        parsed = _default_parsed()
        BaseLLMAdapter._check_language(parsed)

    def test_english_sentence_detected(self):
        parsed = _default_parsed()
        parsed.final_output.strengths.append(
            "This is a very long english sentence that should be detected"
        )
        with pytest.raises(LanguageViolationError, match="영어 문장 혼입"):
            BaseLLMAdapter._check_language(parsed)


class TestValidateCotConsistency:
    def test_consistent_passes(self):
        parsed = _default_parsed()
        BaseLLMAdapter._validate_cot_consistency(parsed)

    def test_mismatch_detected(self):
        parsed = _default_parsed()
        parsed.cot[0].score = 5
        with pytest.raises(CotMismatchError, match="정합성 위반"):
            BaseLLMAdapter._validate_cot_consistency(parsed)


class TestContainsEnglishSentences:
    @pytest.mark.parametrize("text,expected", [
        ("한국어만 있는 문장입니다.", False),
        ("This sentence contains many english words here", True),
        ("단어 keyword 하나는 괜찮음", False),
        ("The quick brown fox jumps over", True),
        ("This is an english sentence here", False),
    ])
    def test_detection(self, text, expected):
        assert _contains_english_sentences(text) == expected


class TestFlattenScores:
    def test_all_items_present(self):
        flat = _flatten_scores(_default_scores())
        assert set(flat.keys()) == VALID_ITEMS


# ── 비용/토큰 테스트 ─────────────────────────────────────────────

class TestEstimateCost:
    def test_openai_cost(self):
        from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter.__new__(OpenAIAdapter)
        adapter.model = "gpt-4o-2024-08-06"
        cost = adapter._estimate_cost(1000, 500)
        expected = (Decimal("1000") * Decimal("2.50") + Decimal("500") * Decimal("10.00")) / Decimal("1000000")
        assert cost == expected.quantize(Decimal("0.000001"))

    def test_openai_mini_cost(self):
        from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter.__new__(OpenAIAdapter)
        adapter.model = "gpt-4o-mini"
        cost = adapter._estimate_cost(1000, 500)
        expected = (Decimal("1000") * Decimal("0.15") + Decimal("500") * Decimal("0.60")) / Decimal("1000000")
        assert cost == expected.quantize(Decimal("0.000001"))

    def test_unknown_model_uses_default(self):
        from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter.__new__(OpenAIAdapter)
        adapter.model = "gpt-999-unknown"
        cost = adapter._estimate_cost(1000, 500)
        assert cost > 0


class TestShouldNotRetry:
    def test_openai_quota_exceeded(self):
        from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter.__new__(OpenAIAdapter)
        exc = RuntimeError("insufficient_quota: exceeded your current quota")
        assert adapter._should_not_retry(exc) is False

    def test_generic_error_retryable(self):
        from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter.__new__(OpenAIAdapter)
        assert adapter._should_not_retry(RuntimeError("network error")) is False


# ── 중복 제거 테스트 ──────────────────────────────────────────────

class TestDeduplicateRanked:
    def test_removes_similar(self):
        adapter = StubAdapter()
        items = [
            "학습 목표가 명확하게 제시되었습니다",
            "학습 목표가 명확하게 제시됨",
            "실습 연계가 부족합니다",
        ]
        result = adapter._deduplicate_ranked(items)
        assert len(result) <= len(items)
        assert len(result) >= 2

    def test_empty_returns_padding(self):
        adapter = StubAdapter()
        result = adapter._deduplicate_ranked([])
        assert len(result) == 10

    def test_unique_items_kept(self):
        adapter = StubAdapter()
        items = [
            "학습 목표가 명확하게 제시되었습니다",
            "실습 전환이 자연스럽게 이루어집니다",
            "비유를 통한 개념 설명이 효과적입니다",
            "핵심 내용을 반복 강조하여 이해도를 높였습니다",
            "질문에 대한 응답이 충분합니다",
            "오류 대응이 체계적으로 진행되었습니다",
            "참여 유도가 적극적으로 이루어졌습니다",
            "선행 개념을 충분히 짚어주었습니다",
            "강의 마무리 요약이 명확합니다",
            "예시가 학습 수준에 적합합니다",
            "전날 복습이 오늘 강의와 잘 연결됩니다",
        ]
        result = adapter._deduplicate_ranked(items)
        assert len(result) >= 10


class TestNormalizeCount:
    def test_enough_items_trimmed(self):
        adapter = StubAdapter()
        items = [f"항목{i}" for i in range(15)]
        result = adapter._normalize_count(items, [])
        assert len(result) == 10

    def test_insufficient_padded(self):
        adapter = StubAdapter()
        llm_items = ["A", "B", "C"]
        raw_items = [f"원본{i}" for i in range(20)]
        result = adapter._normalize_count(llm_items, raw_items)
        assert len(result) == 10
        assert result[:3] == ["A", "B", "C"]


# ── aggregate_results 테스트 ──────────────────────────────────────

class TestAggregateResults:
    def test_success(self):
        adapter = StubAdapter()
        items, usage = adapter.aggregate_results(
            ["강점1", "강점2"], "강점", "scores", "trends",
        )
        assert len(items) == 10

    def test_refusal_propagated(self):
        adapter = StubAdapter()
        adapter._call_aggregate_sync = lambda _: (_ for _ in ()).throw(
            RefusalError("거부")
        )
        with pytest.raises(RefusalError):
            adapter.aggregate_results(["x"], "강점", "", "")

    def test_generic_error_falls_back(self):
        adapter = StubAdapter()
        adapter._call_aggregate_sync = lambda _: (_ for _ in ()).throw(
            RuntimeError("API 오류")
        )
        raw_items = [
            "학습 목표가 명확하게 제시되었습니다",
            "실습 전환이 자연스럽게 이루어집니다",
            "비유를 통한 개념 설명이 효과적입니다",
            "핵심 내용을 반복 강조하여 이해도를 높였습니다",
            "질문에 대한 응답이 충분하고 명확합니다",
            "오류 대응이 체계적으로 진행되었습니다",
            "참여 유도가 적극적으로 이루어졌습니다",
            "선행 개념을 충분히 짚어주었습니다",
            "강의 마무리 요약이 상세하게 제공됩니다",
            "예시가 학습 수준에 적합하게 선정되었습니다",
            "전날 복습이 오늘 강의와 잘 연결됩니다",
        ]
        items, usage = adapter.aggregate_results(
            raw_items, "강점", "", "",
        )
        assert len(items) == 10
        assert usage.total_tokens == 0


# ── compute_reliability 테스트 ────────────────────────────────────

class TestComputeReliability:
    def test_perfect_reliability(self):
        from LLMEngine.core.ports import EvidenceValidationDetail

        detail = EvidenceValidationDetail(
            passed=[Evidence(item="explanation_sequence", quote="q", reason="r")],
            total_requested=1, total_passed=1,
            pass_ratio=1.0, similarity_scores=[100.0], avg_similarity=100.0,
        )
        scores = _default_scores()
        rel = BaseLLMAdapter._compute_reliability(detail, scores, hallucination_retries=0)
        assert rel.overall_reliability_score > 0.5
        assert rel.evidence_pass_ratio == 1.0

    def test_zero_hallucination_retries_bonus(self):
        from LLMEngine.core.ports import EvidenceValidationDetail

        detail = EvidenceValidationDetail(
            passed=[], total_requested=0, total_passed=0,
            pass_ratio=0.0, similarity_scores=[], avg_similarity=0.0,
        )
        scores = _default_scores()
        r0 = BaseLLMAdapter._compute_reliability(detail, scores, hallucination_retries=0)
        r3 = BaseLLMAdapter._compute_reliability(detail, scores, hallucination_retries=3)
        assert r0.overall_reliability_score > r3.overall_reliability_score
