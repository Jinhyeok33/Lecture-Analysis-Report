"""ab_testing.py 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from LLMEngine.core.ab_testing import ABTestRunner, ABComparison
from LLMEngine.core.schemas import ChunkScores, LectureStructureScores, ConceptClarityScores, PracticeLinkageScores, InteractionScores
from LLMEngine.tests.conftest import FakeLLMProvider, make_chunk_metadata, make_chunk_result


class TestABTestRunner:
    def test_requires_two_providers(self):
        with pytest.raises(ValueError, match="최소 2개"):
            ABTestRunner([FakeLLMProvider()])

    def test_run_comparison(self):
        p1 = FakeLLMProvider()
        p2 = FakeLLMProvider()
        runner = ABTestRunner([p1, p2])
        chunks = [make_chunk_metadata(chunk_id=1, total_chunks=1)]
        results = runner.run_comparison(chunks)
        assert len(results) == 2
        assert results[0].model_name == "fake-model"
        assert len(results[0].chunk_results) == 1

    def test_compare_scores_identical(self):
        p1 = FakeLLMProvider()
        p2 = FakeLLMProvider()
        runner = ABTestRunner([p1, p2])
        chunks = [make_chunk_metadata(chunk_id=1, total_chunks=1)]
        results = runner.run_comparison(chunks)
        comparisons = runner.compare_scores(results)
        assert len(comparisons) == 1
        assert comparisons[0].agreement_ratio == 1.0

    def test_compare_scores_different(self):
        different_scores = ChunkScores(
            lecture_structure=LectureStructureScores(
                learning_objective_intro=5, previous_lesson_linkage=5,
                explanation_sequence=5, key_point_emphasis=5, closing_summary=5,
            ),
            concept_clarity=ConceptClarityScores(
                concept_definition=5, analogy_example_usage=5, prerequisite_check=5,
            ),
            practice_linkage=PracticeLinkageScores(
                example_appropriateness=5, practice_transition=5, error_handling=5,
            ),
            interaction=InteractionScores(
                participation_induction=5, question_response_sufficiency=5,
            ),
        )
        p1 = FakeLLMProvider()
        p2 = FakeLLMProvider(make_chunk_result(scores=different_scores))
        runner = ABTestRunner([p1, p2])
        chunks = [make_chunk_metadata(chunk_id=1, total_chunks=1)]
        results = runner.run_comparison(chunks)
        comparisons = runner.compare_scores(results)
        assert comparisons[0].agreement_ratio < 1.0

    def test_save_comparison(self, tmp_path):
        p1 = FakeLLMProvider()
        p2 = FakeLLMProvider()
        runner = ABTestRunner([p1, p2])
        chunks = [make_chunk_metadata(chunk_id=1, total_chunks=1)]
        results = runner.run_comparison(chunks)
        comparisons = runner.compare_scores(results)
        out = tmp_path / "ab_result.json"
        runner.save_comparison(results, comparisons, out)
        assert out.exists()
        import json
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data["models"]) == 2
