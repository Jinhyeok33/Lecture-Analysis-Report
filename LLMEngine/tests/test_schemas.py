"""schemas.py 단위 테스트 — Pydantic 모델 검증, 범위 제약, 정규화."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from LLMEngine.core.schemas import (
    ChunkMetadata, ChunkResult, ChunkScores, ChunkStatus, Evidence,
    FailureClass, ItemEvaluation, LLMInternalResponse,
    LectureStructureScores, ConceptClarityScores, PracticeLinkageScores,
    InteractionScores, ParsedScript, ReliabilityMetrics, ScriptLine,
    SummaryScores, SummaryLectureStructureScores, SummaryConceptClarityScores,
    SummaryPracticeLinkageScores, SummaryInteractionScores,
    TokenUsage, VALID_ITEMS, _normalize_item_key, ChunkStateRecord,
)


class TestTokenUsage:
    def test_add(self):
        a = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150, llm_call_count=1)
        b = TokenUsage(prompt_tokens=200, completion_tokens=80, total_tokens=280, llm_call_count=2)
        c = a + b
        assert c.prompt_tokens == 300
        assert c.total_tokens == 430
        assert c.llm_call_count == 3

    def test_default_zero(self):
        t = TokenUsage()
        assert t.total_tokens == 0
        assert str(t.estimated_cost_usd) == "0"


class TestScoreValidation:
    def test_valid_score(self):
        ls = LectureStructureScores(
            explanation_sequence=5, key_point_emphasis=1,
        )
        assert ls.explanation_sequence == 5
        assert ls.learning_objective_intro is None

    def test_score_out_of_range_high(self):
        with pytest.raises(ValidationError):
            LectureStructureScores(explanation_sequence=6, key_point_emphasis=3)

    def test_score_out_of_range_low(self):
        with pytest.raises(ValidationError):
            LectureStructureScores(explanation_sequence=0, key_point_emphasis=3)

    def test_optional_null_allowed(self):
        ls = LectureStructureScores(
            learning_objective_intro=None, previous_lesson_linkage=None,
            explanation_sequence=3, key_point_emphasis=3, closing_summary=None,
        )
        assert ls.learning_objective_intro is None


class TestEvidence:
    def test_valid_item(self):
        e = Evidence(item="explanation_sequence", quote="test", reason="reason")
        assert e.item == "explanation_sequence"

    def test_item_normalization(self):
        e = Evidence(item="Explanation-Sequence", quote="test", reason="reason")
        assert e.item == "explanation_sequence"

    def test_category_maps_to_default(self):
        e = Evidence(item="lecture_structure", quote="test", reason="reason")
        assert e.item == "explanation_sequence"

    def test_invalid_item_raises(self):
        with pytest.raises(ValidationError):
            Evidence(item="nonexistent_item", quote="test", reason="reason")

    def test_empty_quote_rejected(self):
        with pytest.raises(ValidationError):
            Evidence(item="explanation_sequence", quote="", reason="reason")


class TestItemEvaluation:
    def test_valid(self):
        ie = ItemEvaluation(
            item="concept_definition", quote="발화", anchor="4점 앵커", score=4,
        )
        assert ie.item == "concept_definition"

    def test_invalid_item(self):
        with pytest.raises(ValidationError):
            ItemEvaluation(item="bogus", quote="q", anchor="a", score=3)

    def test_score_null_allowed(self):
        ie = ItemEvaluation(item="closing_summary", quote=None, anchor="N/A", score=None)
        assert ie.score is None


class TestChunkResult:
    def test_valid_time(self):
        from LLMEngine.tests.conftest import make_chunk_result
        r = make_chunk_result(start_time="09:30", end_time="09:42")
        assert r.start_time == "09:30"

    def test_invalid_time_format(self):
        from LLMEngine.tests.conftest import make_chunk_result
        with pytest.raises(ValidationError):
            make_chunk_result(start_time="25:00")

    def test_invalid_time_range(self):
        from LLMEngine.tests.conftest import make_chunk_result
        with pytest.raises(ValidationError):
            make_chunk_result(start_time="09:60")


class TestParsedScript:
    def test_empty_lines_raises(self):
        with pytest.raises(ValidationError):
            ParsedScript(lines=[], parse_failure_count=0)

    def test_valid(self):
        ps = ParsedScript(
            lines=[ScriptLine(timestamp="00:00:00", speaker_id="강사", text="안녕하세요")],
        )
        assert len(ps.lines) == 1


class TestNormalizeItemKey:
    @pytest.mark.parametrize("input_val,expected", [
        ("Explanation Sequence", "explanation_sequence"),
        ("error-handling", "error_handling"),
        ("  CONCEPT_DEFINITION  ", "concept_definition"),
    ])
    def test_normalization(self, input_val, expected):
        assert _normalize_item_key(input_val) == expected


class TestSummaryScoresFloat:
    def test_rounding(self):
        s = SummaryLectureStructureScores(
            explanation_sequence=3.14159, key_point_emphasis=4.567,
        )
        assert s.explanation_sequence == 3.1
        assert s.key_point_emphasis == 4.6

    def test_out_of_range(self):
        with pytest.raises(ValidationError):
            SummaryConceptClarityScores(
                concept_definition=0.5, analogy_example_usage=3.0, prerequisite_check=3.0,
            )


class TestChunkStateRecord:
    def test_basic(self):
        r = ChunkStateRecord(lecture_id="lec01", chunk_id=1, status="PROCESSING")
        assert r.status == "PROCESSING"
        assert r.result is None
