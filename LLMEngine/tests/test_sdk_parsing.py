"""SDK 응답 객체 mock 기반 파싱 테스트.

openai/google-genai SDK를 설치하지 않아도 실행 가능하다.
SDK 응답 구조를 SimpleNamespace로 재현하여 _parse_structured_response,
_extract_usage, _extract_parsed, _parse_gemini_response 경로를 검증한다.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from LLMEngine.core.schemas import (
    ChunkResultPayload, ChunkScores, ConceptClarityScores, Evidence,
    InteractionScores, ItemEvaluation, LLMInternalResponse,
    LectureStructureScores, PracticeLinkageScores, RefinedList, VALID_ITEMS,
)
from LLMEngine.core.exceptions import RefusalError, TruncatedResponseError
from LLMEngine.infrastructure.llm.base_adapter import _flatten_scores


def _make_scores() -> ChunkScores:
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


def _make_cot(scores: ChunkScores) -> list[ItemEvaluation]:
    flat = _flatten_scores(scores)
    return [
        ItemEvaluation(item=item, quote="인용", anchor="3점: 기본", score=val)
        for item, val in flat.items()
    ]


def _make_parsed_response() -> LLMInternalResponse:
    scores = _make_scores()
    return LLMInternalResponse(
        structured_thought_process=_make_cot(scores),
        final_output=ChunkResultPayload(
            scores=scores,
            strengths=["강점"],
            issues=["이슈"],
            evidence=[Evidence(item="explanation_sequence", quote="인용", reason="사유")],
        ),
    )


# ── OpenAI 파싱 테스트 ──────────────────────────────────────────────

class TestOpenAIExtractParsed:
    """OpenAIAdapter._extract_parsed 정적 메서드 검증."""

    @staticmethod
    def _make_openai_response(
        *,
        parsed: object | None = None,
        refusal: str | None = None,
        finish_reason: str = "stop",
    ) -> SimpleNamespace:
        message = SimpleNamespace(parsed=parsed, refusal=refusal)
        choice = SimpleNamespace(finish_reason=finish_reason, message=message)
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        return SimpleNamespace(choices=[choice], usage=usage)

    def test_success_path(self):
        from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter
        expected = _make_parsed_response()
        resp = self._make_openai_response(parsed=expected)
        result = OpenAIAdapter._extract_parsed(resp, check_truncation=True)
        assert result is expected

    def test_truncation_detected(self):
        from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter
        resp = self._make_openai_response(parsed="dummy", finish_reason="length")
        with pytest.raises(TruncatedResponseError, match="잘렸습니다"):
            OpenAIAdapter._extract_parsed(resp, check_truncation=True)

    def test_refusal_detected(self):
        from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter
        resp = self._make_openai_response(refusal="content policy violation")
        with pytest.raises(RefusalError, match="모델 거부"):
            OpenAIAdapter._extract_parsed(resp)

    def test_empty_choices_raises(self):
        from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter
        resp = SimpleNamespace(choices=[])
        with pytest.raises(RuntimeError, match="choices"):
            OpenAIAdapter._extract_parsed(resp)

    def test_none_parsed_raises(self):
        from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter
        resp = self._make_openai_response(parsed=None)
        with pytest.raises(RuntimeError, match="파싱 결과가 비어"):
            OpenAIAdapter._extract_parsed(resp)


class TestOpenAIExtractUsage:
    def test_normal_usage(self):
        from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter
        adapter = OpenAIAdapter.__new__(OpenAIAdapter)
        resp = SimpleNamespace(usage=SimpleNamespace(
            prompt_tokens=200, completion_tokens=100, total_tokens=300,
        ))
        pt, ct, tt = adapter._extract_usage(resp)
        assert (pt, ct, tt) == (200, 100, 300)

    def test_no_usage(self):
        from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter
        adapter = OpenAIAdapter.__new__(OpenAIAdapter)
        resp = SimpleNamespace(usage=None)
        assert adapter._extract_usage(resp) == (0, 0, 0)


class TestOpenAIParseStructuredResponse:
    def test_delegates_to_extract_parsed(self):
        from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter
        adapter = OpenAIAdapter.__new__(OpenAIAdapter)
        expected = _make_parsed_response()
        message = SimpleNamespace(parsed=expected, refusal=None)
        choice = SimpleNamespace(finish_reason="stop", message=message)
        resp = SimpleNamespace(choices=[choice])
        result = adapter._parse_structured_response(resp)
        assert result is expected


# ── Gemini 파싱 테스트 ──────────────────────────────────────────────

class TestGeminiParseStructuredResponse:
    """GeminiAdapter._parse_structured_response 검증."""

    @staticmethod
    def _make_gemini_response(
        *,
        parsed: object | None = None,
        text: str | None = None,
        block_reason: object = None,
        finish_reason: object = None,
    ) -> SimpleNamespace:
        feedback = SimpleNamespace(block_reason=block_reason) if block_reason else None
        candidate = SimpleNamespace(finish_reason=finish_reason)
        usage = SimpleNamespace(
            prompt_token_count=100, candidates_token_count=50, total_token_count=150,
        )
        return SimpleNamespace(
            prompt_feedback=feedback,
            candidates=[candidate],
            parsed=parsed,
            text=text,
            usage_metadata=usage,
        )

    def test_parsed_object_returned(self):
        from LLMEngine.infrastructure.llm.gemini_adapter import GeminiAdapter
        adapter = GeminiAdapter.__new__(GeminiAdapter)
        expected = _make_parsed_response()
        resp = self._make_gemini_response(parsed=expected, text="{}")
        result = adapter._parse_structured_response(resp)
        assert result is expected

    def test_json_text_fallback(self):
        from LLMEngine.infrastructure.llm.gemini_adapter import GeminiAdapter
        adapter = GeminiAdapter.__new__(GeminiAdapter)
        parsed = _make_parsed_response()
        json_text = parsed.model_dump_json()
        resp = self._make_gemini_response(parsed=None, text=json_text)
        result = adapter._parse_structured_response(resp)
        assert isinstance(result, LLMInternalResponse)

    def test_block_reason_raises_refusal(self):
        from LLMEngine.infrastructure.llm.gemini_adapter import GeminiAdapter
        adapter = GeminiAdapter.__new__(GeminiAdapter)
        resp = self._make_gemini_response(
            block_reason="SAFETY", parsed="x", text="x",
        )
        with pytest.raises(RefusalError, match="차단"):
            adapter._parse_structured_response(resp)

    def test_safety_finish_reason_raises(self):
        from LLMEngine.infrastructure.llm.gemini_adapter import GeminiAdapter
        adapter = GeminiAdapter.__new__(GeminiAdapter)
        resp = self._make_gemini_response(
            finish_reason="SAFETY", parsed="x", text="x",
        )
        with pytest.raises(RefusalError, match="safety"):
            adapter._parse_structured_response(resp)

    def test_max_tokens_finish_reason_raises(self):
        from LLMEngine.infrastructure.llm.gemini_adapter import GeminiAdapter
        adapter = GeminiAdapter.__new__(GeminiAdapter)
        resp = self._make_gemini_response(
            finish_reason="MAX_TOKENS", parsed="x", text="x",
        )
        with pytest.raises(TruncatedResponseError, match="토큰 한도"):
            adapter._parse_structured_response(resp)

    def test_empty_response_raises(self):
        from LLMEngine.infrastructure.llm.gemini_adapter import GeminiAdapter
        adapter = GeminiAdapter.__new__(GeminiAdapter)
        resp = self._make_gemini_response(parsed=None, text="")
        with pytest.raises(RuntimeError, match="비어"):
            adapter._parse_structured_response(resp)


class TestGeminiExtractUsage:
    def test_normal(self):
        from LLMEngine.infrastructure.llm.gemini_adapter import GeminiAdapter
        adapter = GeminiAdapter.__new__(GeminiAdapter)
        resp = SimpleNamespace(usage_metadata=SimpleNamespace(
            prompt_token_count=200, candidates_token_count=100, total_token_count=300,
        ))
        assert adapter._extract_usage(resp) == (200, 100, 300)

    def test_none_metadata(self):
        from LLMEngine.infrastructure.llm.gemini_adapter import GeminiAdapter
        adapter = GeminiAdapter.__new__(GeminiAdapter)
        resp = SimpleNamespace(usage_metadata=None)
        assert adapter._extract_usage(resp) == (0, 0, 0)


class TestGeminiParseGenericResponse:
    def test_dict_parsed_validates(self):
        from LLMEngine.infrastructure.llm.gemini_adapter import GeminiAdapter
        parsed_dict = _make_parsed_response().model_dump()
        resp = SimpleNamespace(parsed=parsed_dict, text=None)
        result = GeminiAdapter._parse_gemini_response(resp, LLMInternalResponse)
        assert isinstance(result, LLMInternalResponse)

    def test_refined_list_from_text(self):
        from LLMEngine.infrastructure.llm.gemini_adapter import GeminiAdapter
        rl = RefinedList(items=[f"항목{i}" for i in range(10)])
        resp = SimpleNamespace(parsed=None, text=rl.model_dump_json())
        result = GeminiAdapter._parse_gemini_response(resp, RefinedList)
        assert isinstance(result, RefinedList)
        assert len(result.items) == 10
