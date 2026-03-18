"""강의 스크립트 분석을 위한 고수준 파이프라인 (오케스트레이터)."""

from __future__ import annotations

import asyncio
import sys
import json
import logging
import concurrent.futures
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.llm_engine.core.config import LLMEngineConfig
from src.llm_engine.core.ports import ILLMProvider, IRepository
from src.llm_engine.core.schemas import (
    AggregatedResult, ChunkMetadata, ChunkResult,
    ChunkScores, LectureStructureScores, ConceptClarityScores,
    PracticeLinkageScores, InteractionScores
)
from src.llm_engine.application.chunk_processor import ChunkProcessor
from src.llm_engine.application.aggregator import ResultAggregator
from src.llm_engine.application.prompts import build_user_prompt, SYSTEM_PROMPT
from src.llm_engine.application.validation import validate_evidence
from src.common.naming import (
    lecture_id_from_transcript_path,
    llm_chunks_json_path,
    llm_json_path,
)

logger = logging.getLogger(__name__)

PREVIOUS_CHUNK_TAIL_MAX_CHARS = 1500

class LectureAnalyzerService:
    def __init__(
        self,
        llm_provider: ILLMProvider,
        repository: IRepository,
        config: LLMEngineConfig | None = None,
    ) -> None:
        self.config = config or LLMEngineConfig.default()
        self.llm = llm_provider
        self.repo = repository
        self.chunker = ChunkProcessor()
        self.aggregator = ResultAggregator(self.llm)

    @staticmethod
    def _inject_previous_chunk_tail(chunks: list[ChunkMetadata]) -> list[ChunkMetadata]:
        if len(chunks) <= 1:
            return list(chunks)
        out: list[ChunkMetadata] = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_text = chunks[i - 1].text
            tail = prev_text[-PREVIOUS_CHUNK_TAIL_MAX_CHARS:] if len(prev_text) > PREVIOUS_CHUNK_TAIL_MAX_CHARS else prev_text
            out.append(chunks[i].model_copy(update={"previous_chunk_tail": tail or None}))
        return out

    def _get_fallback_result(self, chunk_data: ChunkMetadata) -> ChunkResult:
        return ChunkResult(
            chunk_id=chunk_data.chunk_id,
            start_time=chunk_data.start_time,
            end_time=chunk_data.end_time,
            scores=ChunkScores(
                lecture_structure=LectureStructureScores(
                    learning_objective_intro=None,
                    previous_lesson_linkage=None,
                    explanation_sequence=3,
                    key_point_emphasis=3,
                    closing_summary=None
                ),
                concept_clarity=ConceptClarityScores(
                    concept_definition=3, analogy_example_usage=3, prerequisite_check=3
                ),
                practice_linkage=PracticeLinkageScores(
                    example_appropriateness=3, practice_transition=3, error_handling=3
                ),
                interaction=InteractionScores(
                    participation_induction=3, question_response_sufficiency=3
                )
            ),
            strengths=["특이사항 없음"],
            issues=["특이사항 없음"],
            evidence=[]
        )

    def process_chunks(
        self,
        lecture_id: str,
        chunks: list[ChunkMetadata],
        use_async: bool = True,
        max_concurrency: int = 3,
    ) -> tuple[list[ChunkResult], AggregatedResult]:
        completed = self.repo.get_completed_chunks(lecture_id)
        completed_map = {c.chunk_id: c for c in completed}

        pending_chunks = [c for c in chunks if c.chunk_id not in completed_map]
        results_map = {c.chunk_id: c for c in completed}

        if pending_chunks:
            if use_async:
                logger.info(f"[{lecture_id}] {len(pending_chunks)}개 청크 비동기 분석 시작 (동시성: {max_concurrency})")
                
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    def _run_in_thread():
                        return asyncio.run(self._process_chunks_async(lecture_id, pending_chunks, max_concurrency))
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        new_results = pool.submit(_run_in_thread).result()
                else:
                    new_results = asyncio.run(self._process_chunks_async(lecture_id, pending_chunks, max_concurrency))

                for r in new_results:
                    results_map[r.chunk_id] = r
            else:
                logger.info(f"[{lecture_id}] {len(pending_chunks)}개 청크 동기 분석 시작")
                for chunk in pending_chunks:
                    try:
                        self.repo.save_chunk_state(lecture_id, chunk.chunk_id, "PROCESSING")
                        res = self.llm.analyze_chunk(chunk)
                        self.repo.save_chunk_state(lecture_id, chunk.chunk_id, "SUCCESS", res)
                        results_map[chunk.chunk_id] = res
                    except Exception as e:
                        self.repo.save_chunk_state(lecture_id, chunk.chunk_id, "FAILED")
                        logger.error(f"[{lecture_id}] 청크 {chunk.chunk_id} 실패: {e}")
                        res = self._get_fallback_result(chunk)
                        results_map[chunk.chunk_id] = res

        final_results = [results_map[c.chunk_id] for c in chunks if c.chunk_id in results_map]
        aggregated = self.aggregator.aggregate(final_results)
        
        return final_results, aggregated

    async def _process_chunks_async(
        self, lecture_id: str, chunks: list[ChunkMetadata], max_concurrency: int
    ) -> list[ChunkResult]:
        sem = asyncio.Semaphore(max_concurrency)

        async def analyze_with_sem(chunk: ChunkMetadata) -> ChunkResult:
            async with sem:
                try:
                    self.repo.save_chunk_state(lecture_id, chunk.chunk_id, "PROCESSING")
                    res = await getattr(self.llm, "analyze_chunk_async")(chunk)
                    self.repo.save_chunk_state(lecture_id, chunk.chunk_id, "SUCCESS", res)
                    return res
                except Exception as e:
                    self.repo.save_chunk_state(lecture_id, chunk.chunk_id, "FAILED")
                    logger.error(f"[{lecture_id}] 청크 {chunk.chunk_id} (Async) 실패: {e}")
                    return self._get_fallback_result(chunk)

        return await asyncio.gather(*[analyze_with_sem(c) for c in chunks])

    async def process_chunks_async(
        self,
        lecture_id: str,
        chunks: list[ChunkMetadata],
        max_concurrency: int = 3,
    ) -> tuple[list[ChunkResult], AggregatedResult]:
        completed = self.repo.get_completed_chunks(lecture_id)
        completed_map = {c.chunk_id: c for c in completed}
        pending_chunks = [c for c in chunks if c.chunk_id not in completed_map]
        results_map = {c.chunk_id: c for c in completed}

        if pending_chunks:
            logger.info(f"[{lecture_id}] {len(pending_chunks)}개 청크 비동기 분석 (동시성: {max_concurrency})")
            new_results = await self._process_chunks_async(lecture_id, pending_chunks, max_concurrency)
            for r in new_results:
                results_map[r.chunk_id] = r

        final_results = [results_map[c.chunk_id] for c in chunks if c.chunk_id in results_map]
        aggregated = self.aggregator.aggregate(final_results)
        return final_results, aggregated

    async def process_lecture_async(
        self,
        lecture_id: str,
        transcript_path: str | Path,
        chunk_duration_minutes: int | None = None,
        overlap_minutes: int | None = None,
        max_concurrency: int = 3,
    ) -> tuple[list[ChunkResult], AggregatedResult]:
        duration = chunk_duration_minutes or self.config.chunk_duration_minutes
        overlap = overlap_minutes if overlap_minutes is not None else self.config.overlap_minutes
        raw_chunks = self.chunker.process(
            transcript_path,
            chunk_duration_minutes=duration,
            overlap_minutes=overlap,
        )
        chunks = self._inject_previous_chunk_tail(raw_chunks)
        return await self.process_chunks_async(lecture_id, chunks, max_concurrency=max_concurrency)

    def process_lecture(
        self,
        lecture_id: str,
        transcript_path: str | Path,
        chunk_duration_minutes: int | None = None,
        overlap_minutes: int | None = None,
        use_async: bool = True,
        max_concurrency: int = 3,
    ) -> tuple[list[ChunkResult], AggregatedResult]:
        duration = chunk_duration_minutes or self.config.chunk_duration_minutes
        overlap = overlap_minutes if overlap_minutes is not None else self.config.overlap_minutes

        raw_chunks = self.chunker.process(
            transcript_path,
            chunk_duration_minutes=duration,
            overlap_minutes=overlap,
        )
        chunks = self._inject_previous_chunk_tail(raw_chunks)

        return self.process_chunks(lecture_id, chunks, use_async=use_async, max_concurrency=max_concurrency)

    def save_files(
        self,
        chunk_results: list[ChunkResult],
        aggregated_result: AggregatedResult,
        output_dir: str | Path,
        lecture_id: str,
    ) -> tuple[Path, Path]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        chunk_file = llm_chunks_json_path(output_path, lecture_id)
        aggregated_file = llm_json_path(output_path, lecture_id)

        with chunk_file.open("w", encoding="utf-8") as handle:
            json.dump([item.model_dump() for item in chunk_results], handle, ensure_ascii=False, indent=2)

        with aggregated_file.open("w", encoding="utf-8") as handle:
            json.dump(aggregated_result.model_dump(), handle, ensure_ascii=False, indent=2)

        return chunk_file, aggregated_file

    def run(
        self,
        transcript_path: str | Path,
        output_dir: str | Path | None = None,
        lecture_id: str | None = None,
        chunk_duration_minutes: int | None = None,
        overlap_minutes: int | None = None,
        use_async: bool = True,
        max_concurrency: int = 3,
    ) -> tuple[list[ChunkResult], AggregatedResult] | tuple[list[ChunkResult], AggregatedResult, Path, Path]:
        base_id = lecture_id or lecture_id_from_transcript_path(transcript_path)
        lid = base_id

        chunk_results, aggregated = self.process_lecture(
            lecture_id=lid,
            transcript_path=transcript_path,
            chunk_duration_minutes=chunk_duration_minutes,
            overlap_minutes=overlap_minutes,
            use_async=use_async,
            max_concurrency=max_concurrency,
        )

        if output_dir is None:
            return chunk_results, aggregated

        chunk_path, agg_path = self.save_files(chunk_results, aggregated, output_dir, lid)
        return chunk_results, aggregated, chunk_path, agg_path
