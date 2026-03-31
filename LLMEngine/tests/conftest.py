"""테스트 공용 fixture.

mock 데이터 경로, 최소 ChunkResult/ChunkMetadata 팩토리 등을 제공한다.
LLM API 호출은 일절 없다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

import pytest

from LLMEngine.core.schemas import (
    ChunkMetadata, ChunkResult, ChunkScores, ChunkStatus,
    ConceptClarityScores, Evidence, InteractionScores,
    LectureStructureScores, PracticeLinkageScores,
    ReliabilityMetrics, TokenUsage, ChunkStateRecord,
)
from LLMEngine.core.ports import ILLMProvider, IRepository


MOCK_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "dataset" / "mock" / "강의 스크립트" / "2026-03-02_kdt-backendj-21th.txt"
)


@pytest.fixture
def mock_script_path() -> Path:
    assert MOCK_SCRIPT_PATH.exists(), f"mock 데이터 없음: {MOCK_SCRIPT_PATH}"
    return MOCK_SCRIPT_PATH


def make_chunk_metadata(
    chunk_id: int = 1,
    start_time: str = "00:00",
    end_time: str = "00:10",
    text: str = "강사: 테스트 발화입니다.",
    total_chunks: int = 3,
) -> ChunkMetadata:
    return ChunkMetadata(
        chunk_id=chunk_id,
        start_time=start_time,
        end_time=end_time,
        text=text,
        line_count=max(1, text.count("\n") + 1),
        word_count=max(1, len(text.split())),
        total_chunks=total_chunks,
    )


def make_chunk_result(
    chunk_id: int = 1,
    start_time: str = "00:00",
    end_time: str = "00:10",
    status: ChunkStatus = ChunkStatus.SUCCESS,
    is_fallback: bool = False,
    scores: ChunkScores | None = None,
) -> ChunkResult:
    if scores is None:
        scores = ChunkScores(
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
    return ChunkResult(
        chunk_id=chunk_id,
        start_time=start_time,
        end_time=end_time,
        scores=scores,
        strengths=["학습 목표를 명확히 제시함"],
        issues=["실습 연결이 부족함"],
        evidence=[
            Evidence(item="explanation_sequence", quote="테스트 발화입니다", reason="순서대로 설명함"),
        ],
        status=status,
        is_fallback=is_fallback,
        token_usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        reliability=ReliabilityMetrics(
            evidence_pass_ratio=0.8, hallucination_retries=0,
            avg_evidence_similarity=90.0, score_evidence_consistency=0.8,
            overall_reliability_score=0.8,
        ),
    )


class FakeLLMProvider(ILLMProvider):
    """LLM API를 호출하지 않는 fake adapter."""

    def __init__(self, chunk_result: ChunkResult | None = None):
        self._result = chunk_result or make_chunk_result()

    @property
    def model_name(self) -> str:
        return "fake-model"

    def analyze_chunk(self, chunk: ChunkMetadata) -> ChunkResult:
        return self._result.model_copy(update={
            "chunk_id": chunk.chunk_id,
            "start_time": chunk.start_time,
            "end_time": chunk.end_time,
        })

    async def analyze_chunk_async(self, chunk: ChunkMetadata) -> ChunkResult:
        return self.analyze_chunk(chunk)

    def aggregate_results(
        self, items: List[str], label: str, scores_context: str, trends: str,
    ) -> Tuple[List[str], TokenUsage]:
        deduped = list(dict.fromkeys(items))[:10]
        if len(deduped) < 10:
            deduped.extend(["집계 패딩"] * (10 - len(deduped)))
        return deduped[:10], TokenUsage(prompt_tokens=50, completion_tokens=30, total_tokens=80)


class InMemoryRepository(IRepository):
    """파일 I/O 없는 in-memory 저장소."""

    def __init__(self):
        self._store: dict[str, dict[str, dict]] = {}

    def save_chunk_state(self, record: ChunkStateRecord) -> None:
        lid = record.lecture_id
        cid = str(record.chunk_id)
        if lid not in self._store:
            self._store[lid] = {}
        self._store[lid][cid] = {
            "status": record.status,
            "result": record.result.model_dump(mode="json") if record.result else None,
            "failure_reason": record.failure_reason,
        }

    def get_completed_chunks(self, lecture_id: str) -> List[ChunkResult]:
        data = self._store.get(lecture_id, {})
        return [
            ChunkResult.model_validate(d["result"])
            for d in data.values()
            if d.get("status") == "SUCCESS" and d.get("result")
        ]
