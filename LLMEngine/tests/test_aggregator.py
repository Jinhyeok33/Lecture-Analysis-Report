"""aggregator.py 단위 테스트 — FakeLLMProvider로 집계 로직 검증."""

from __future__ import annotations

import pytest

from LLMEngine.core.schemas import ChunkStatus
from LLMEngine.application.aggregator import ResultAggregator, _flatten_summary
from LLMEngine.tests.conftest import FakeLLMProvider, make_chunk_result


@pytest.fixture
def aggregator():
    return ResultAggregator(FakeLLMProvider())


class TestFlattenSummary:
    def test_flattens_all_items(self, aggregator):
        results = [make_chunk_result(chunk_id=i) for i in range(1, 4)]
        summary = aggregator._calculate_summary_scores(results)
        flat = _flatten_summary(summary)
        assert "explanation_sequence" in flat
        assert "concept_definition" in flat
        assert isinstance(flat["explanation_sequence"], float)


class TestCalculateSummaryScores:
    def test_single_chunk(self, aggregator):
        results = [make_chunk_result()]
        summary = aggregator._calculate_summary_scores(results)
        assert summary.lecture_structure.explanation_sequence == 4.0

    def test_multiple_chunks_average(self, aggregator):
        from LLMEngine.core.schemas import (
            ChunkScores, LectureStructureScores, ConceptClarityScores,
            PracticeLinkageScores, InteractionScores,
        )
        def scores_with(exp_seq: int) -> ChunkScores:
            return ChunkScores(
                lecture_structure=LectureStructureScores(
                    explanation_sequence=exp_seq, key_point_emphasis=3,
                ),
                concept_clarity=ConceptClarityScores(
                    concept_definition=3, analogy_example_usage=3, prerequisite_check=3,
                ),
                practice_linkage=PracticeLinkageScores(
                    example_appropriateness=3, practice_transition=3, error_handling=3,
                ),
                interaction=InteractionScores(
                    participation_induction=3, question_response_sufficiency=3,
                ),
            )
        r1 = make_chunk_result(chunk_id=1, scores=scores_with(2))
        r2 = make_chunk_result(chunk_id=2, scores=scores_with(4))
        summary = aggregator._calculate_summary_scores([r1, r2])
        assert summary.lecture_structure.explanation_sequence == 3.0


class TestAggregate:
    def test_basic_aggregate(self, aggregator):
        results = [make_chunk_result(chunk_id=i) for i in range(1, 3)]
        agg = aggregator.aggregate(results)

        assert agg.run_metadata.total_chunks == 2
        assert agg.run_metadata.successful_chunks == 2
        assert agg.run_metadata.fallback_chunks == 0
        assert len(agg.llm_aggregated_analysis.overall_strengths) <= 10
        assert len(agg.llm_aggregated_analysis.overall_issues) <= 10
        assert agg.run_metadata.token_usage.total_tokens > 0

    def test_all_fallback_uses_all_chunks(self, aggregator):
        results = [make_chunk_result(chunk_id=1, is_fallback=True)]
        agg = aggregator.aggregate(results)
        assert agg.run_metadata.scored_chunks == 1

    def test_empty_raises(self, aggregator):
        with pytest.raises(ValueError, match="최소 1개"):
            aggregator.aggregate([])


class TestReliabilityAggregation:
    def test_with_metrics(self, aggregator):
        results = [make_chunk_result(chunk_id=i) for i in range(1, 4)]
        rel = aggregator._aggregate_reliability(results)
        assert 0 <= rel.overall_reliability_score <= 1.0
        assert rel.evidence_pass_ratio > 0

    def test_without_metrics(self, aggregator):
        from LLMEngine.tests.conftest import make_chunk_result as mk
        r = mk(chunk_id=1)
        r = r.model_copy(update={"reliability": None})
        rel = aggregator._aggregate_reliability([r])
        assert rel.overall_reliability_score == 1.0


class TestPartitionItemsByScore:
    def test_partition(self, aggregator):
        results = [make_chunk_result()]
        summary = aggregator._calculate_summary_scores(results)
        strengths, issues = aggregator._partition_items_by_score(summary)
        assert isinstance(strengths, list)
        assert isinstance(issues, list)
