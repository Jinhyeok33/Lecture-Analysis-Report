"""Lecture transcript LLM analysis orchestrator."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.common.naming import lecture_id_from_transcript_path, llm_chunks_json_path, llm_json_path
from src.llm_engine.application.aggregator import ResultAggregator
from src.llm_engine.application.chunk_processor import ChunkProcessor
from src.llm_engine.core.config import LLMEngineConfig
from src.llm_engine.core.exceptions import NonRetryableAPIError, RefusalError
from src.llm_engine.core.ports import ILLMProvider, IRepository
from src.llm_engine.core.schemas import (
    AggregatedResult,
    ChunkMetadata,
    ChunkResult,
    ChunkScores,
    ChunkStateRecord,
    ChunkStatus,
    ConceptClarityScores,
    FailureClass,
    InteractionScores,
    LectureStructureScores,
    PREVIOUS_CHUNK_TAIL_MAX_CHARS,
    PracticeLinkageScores,
    ReliabilityMetrics,
)

logger = logging.getLogger(__name__)

NA_FIRST_CHUNK_ONLY = frozenset({"learning_objective_intro", "previous_lesson_linkage"})
NA_LAST_CHUNK_ONLY = frozenset({"closing_summary"})


def _classify_failure(exc: BaseException) -> tuple[ChunkStatus, FailureClass | None]:
    if isinstance(exc, asyncio.CancelledError):
        return ChunkStatus.CANCELLED, FailureClass.PERMANENT
    if isinstance(exc, RefusalError):
        return ChunkStatus.REFUSED, None
    if isinstance(exc, TimeoutError):
        return ChunkStatus.TIMED_OUT, FailureClass.RETRYABLE
    if isinstance(exc, NonRetryableAPIError):
        return ChunkStatus.FAILED, FailureClass.NON_RETRYABLE

    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        if isinstance(cause, RefusalError):
            return ChunkStatus.REFUSED, None
        if isinstance(cause, TimeoutError):
            return ChunkStatus.TIMED_OUT, FailureClass.RETRYABLE
        if isinstance(cause, NonRetryableAPIError):
            return ChunkStatus.FAILED, FailureClass.NON_RETRYABLE

    return ChunkStatus.FAILED, FailureClass.RETRYABLE


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
        self._repo_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="repo_writer")
        self._fallback_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="async_bridge")
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._repo_executor.shutdown(wait=False)
        self._fallback_executor.shutdown(wait=False)

    def __enter__(self) -> "LectureAnalyzerService":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @staticmethod
    def _inject_previous_chunk_tail(chunks: list[ChunkMetadata]) -> list[ChunkMetadata]:
        if len(chunks) <= 1:
            return list(chunks)

        output: list[ChunkMetadata] = [chunks[0]]
        for index in range(1, len(chunks)):
            previous_text = chunks[index - 1].text
            raw_tail = previous_text[-PREVIOUS_CHUNK_TAIL_MAX_CHARS:]
            newline_index = raw_tail.find("\n")
            tail = raw_tail[newline_index + 1 :] if newline_index >= 0 else raw_tail
            output.append(chunks[index].model_copy(update={"previous_chunk_tail": tail or None}))
        return output

    @staticmethod
    def _enforce_na_policy(result: ChunkResult, total_chunks: int) -> ChunkResult:
        is_first = result.chunk_id == 1
        is_last = result.chunk_id == total_chunks
        scores_dump = result.scores.model_dump()
        lecture_structure = scores_dump["lecture_structure"]
        changed = False

        if not is_first:
            for key in NA_FIRST_CHUNK_ONLY:
                if lecture_structure.get(key) is not None:
                    lecture_structure[key] = None
                    changed = True
        if not is_last:
            for key in NA_LAST_CHUNK_ONLY:
                if lecture_structure.get(key) is not None:
                    lecture_structure[key] = None
                    changed = True

        if not changed:
            return result
        return result.model_copy(update={"scores": ChunkScores.model_validate(scores_dump)})

    def _get_fallback_result(
        self,
        chunk: ChunkMetadata,
        *,
        failure_reason: str = "Unknown error",
        status: ChunkStatus = ChunkStatus.FAILED,
        failure_class: FailureClass | None = FailureClass.RETRYABLE,
        retry_count: int = 0,
    ) -> ChunkResult:
        return ChunkResult(
            chunk_id=chunk.chunk_id,
            start_time=chunk.start_time,
            end_time=chunk.end_time,
            scores=ChunkScores(
                lecture_structure=LectureStructureScores(
                    learning_objective_intro=None,
                    previous_lesson_linkage=None,
                    explanation_sequence=3,
                    key_point_emphasis=3,
                    closing_summary=None,
                ),
                concept_clarity=ConceptClarityScores(
                    concept_definition=3,
                    analogy_example_usage=3,
                    prerequisite_check=3,
                ),
                practice_linkage=PracticeLinkageScores(
                    example_appropriateness=3,
                    practice_transition=3,
                    error_handling=3,
                ),
                interaction=InteractionScores(
                    participation_induction=3,
                    question_response_sufficiency=3,
                ),
            ),
            strengths=["분석 실패로 인한 기본값"],
            issues=["분석 실패로 인한 기본값"],
            evidence=[],
            status=status,
            is_fallback=True,
            failure_reason=failure_reason,
            failure_class=failure_class,
            retry_count=retry_count,
            reliability=ReliabilityMetrics(
                evidence_pass_ratio=0.0,
                hallucination_retries=0,
                avg_evidence_similarity=0.0,
                score_evidence_consistency=0.0,
                overall_reliability_score=0.0,
            ),
        )

    def _failure_to_fallback(
        self,
        lecture_id: str,
        chunk: ChunkMetadata,
        exc: BaseException,
    ) -> ChunkResult:
        error_text = str(exc) or type(exc).__name__
        status, failure_class = _classify_failure(exc)
        logger.error(
            "lecture_id=%s chunk_id=%d %s: %s",
            lecture_id,
            chunk.chunk_id,
            type(exc).__name__,
            error_text,
        )
        return self._get_fallback_result(
            chunk,
            failure_reason=error_text,
            status=status,
            failure_class=failure_class,
        )

    def _resume_checkpoint(
        self,
        lecture_id: str,
        chunks: list[ChunkMetadata],
    ) -> tuple[dict[int, ChunkResult], list[ChunkMetadata]]:
        completed = self.repo.get_completed_chunks(lecture_id)
        results_map = {chunk.chunk_id: chunk for chunk in completed}
        pending = [chunk for chunk in chunks if chunk.chunk_id not in results_map]
        return results_map, pending

    def _finalize(
        self,
        chunks: list[ChunkMetadata],
        results_map: dict[int, ChunkResult],
    ) -> tuple[list[ChunkResult], AggregatedResult]:
        total_chunks = len(chunks)
        final_results = [
            self._enforce_na_policy(results_map[chunk.chunk_id], total_chunks)
            for chunk in chunks
            if chunk.chunk_id in results_map
        ]
        aggregated = self.aggregator.aggregate(final_results)
        return final_results, aggregated

    def _run_async_batch(
        self,
        lecture_id: str,
        pending: list[ChunkMetadata],
        max_concurrency: int,
    ) -> list[ChunkResult]:
        coroutine = self._process_chunks_async(lecture_id, pending, max_concurrency)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            timeout_s = self.config.api_timeout_s * len(pending) * (self.config.max_retries + 1)
            return self._fallback_executor.submit(asyncio.run, coroutine).result(timeout=timeout_s)
        return asyncio.run(coroutine)

    def process_chunks(
        self,
        lecture_id: str,
        chunks: list[ChunkMetadata],
        use_async: bool = True,
        max_concurrency: int | None = None,
    ) -> tuple[list[ChunkResult], AggregatedResult]:
        concurrency = max_concurrency or self.config.max_concurrency
        results_map, pending = self._resume_checkpoint(lecture_id, chunks)

        if pending:
            if use_async:
                logger.info(
                    "lecture_id=%s stage=batch pending=%d concurrency=%d",
                    lecture_id,
                    len(pending),
                    concurrency,
                )
                for result in self._run_async_batch(lecture_id, pending, concurrency):
                    results_map[result.chunk_id] = result
            else:
                logger.info(
                    "lecture_id=%s stage=batch_sync pending=%d",
                    lecture_id,
                    len(pending),
                )
                for chunk in pending:
                    self.repo.save_chunk_state(
                        ChunkStateRecord(
                            lecture_id=lecture_id,
                            chunk_id=chunk.chunk_id,
                            status="PROCESSING",
                        )
                    )
                    try:
                        result = self.llm.analyze_chunk(chunk)
                        self.repo.save_chunk_state(
                            ChunkStateRecord(
                                lecture_id=lecture_id,
                                chunk_id=chunk.chunk_id,
                                status="SUCCESS",
                                result=result,
                            )
                        )
                        results_map[result.chunk_id] = result
                    except Exception as exc:
                        self.repo.save_chunk_state(
                            ChunkStateRecord(
                                lecture_id=lecture_id,
                                chunk_id=chunk.chunk_id,
                                status="FAILED",
                                failure_reason=str(exc),
                            )
                        )
                        results_map[chunk.chunk_id] = self._failure_to_fallback(lecture_id, chunk, exc)

        return self._finalize(chunks, results_map)

    async def _process_chunks_async(
        self,
        lecture_id: str,
        chunks: list[ChunkMetadata],
        max_concurrency: int,
    ) -> list[ChunkResult]:
        semaphore = asyncio.Semaphore(max_concurrency)
        loop = asyncio.get_running_loop()

        async def save_record(record: ChunkStateRecord) -> None:
            await loop.run_in_executor(self._repo_executor, self.repo.save_chunk_state, record)

        async def analyze_one(chunk: ChunkMetadata) -> ChunkResult:
            async with semaphore:
                await save_record(
                    ChunkStateRecord(
                        lecture_id=lecture_id,
                        chunk_id=chunk.chunk_id,
                        status="PROCESSING",
                    )
                )
                try:
                    result = await self.llm.analyze_chunk_async(chunk)
                    await save_record(
                        ChunkStateRecord(
                            lecture_id=lecture_id,
                            chunk_id=chunk.chunk_id,
                            status="SUCCESS",
                            result=result,
                        )
                    )
                    return result
                except asyncio.CancelledError:
                    await save_record(
                        ChunkStateRecord(
                            lecture_id=lecture_id,
                            chunk_id=chunk.chunk_id,
                            status="FAILED",
                            failure_reason="CancelledError",
                        )
                    )
                    raise
                except Exception as exc:
                    await save_record(
                        ChunkStateRecord(
                            lecture_id=lecture_id,
                            chunk_id=chunk.chunk_id,
                            status="FAILED",
                            failure_reason=str(exc),
                        )
                    )
                    return self._failure_to_fallback(lecture_id, chunk, exc)

        raw_results = await asyncio.gather(
            *[analyze_one(chunk) for chunk in chunks],
            return_exceptions=True,
        )

        for item in raw_results:
            if isinstance(item, asyncio.CancelledError):
                raise asyncio.CancelledError()

        return [
            self._failure_to_fallback(lecture_id, chunk, item)
            if isinstance(item, BaseException)
            else item
            for chunk, item in zip(chunks, raw_results)
        ]

    async def process_chunks_async(
        self,
        lecture_id: str,
        chunks: list[ChunkMetadata],
        max_concurrency: int | None = None,
    ) -> tuple[list[ChunkResult], AggregatedResult]:
        concurrency = max_concurrency or self.config.max_concurrency
        results_map, pending = self._resume_checkpoint(lecture_id, chunks)

        if pending:
            logger.info(
                "lecture_id=%s stage=batch_async pending=%d concurrency=%d",
                lecture_id,
                len(pending),
                concurrency,
            )
            for result in await self._process_chunks_async(lecture_id, pending, concurrency):
                results_map[result.chunk_id] = result

        return self._finalize(chunks, results_map)

    def _prepare_chunks(
        self,
        transcript_path: str | Path,
        chunk_duration_minutes: int | None,
        overlap_minutes: int | None,
    ) -> list[ChunkMetadata]:
        duration = chunk_duration_minutes or self.config.chunk_duration_minutes
        overlap = overlap_minutes if overlap_minutes is not None else self.config.overlap_minutes
        raw_chunks = self.chunker.process(
            transcript_path,
            chunk_duration_minutes=duration,
            overlap_minutes=overlap,
        )
        total_chunks = len(raw_chunks)
        with_total = [chunk.model_copy(update={"total_chunks": total_chunks}) for chunk in raw_chunks]
        return self._inject_previous_chunk_tail(with_total)

    def process_lecture(
        self,
        lecture_id: str,
        transcript_path: str | Path,
        chunk_duration_minutes: int | None = None,
        overlap_minutes: int | None = None,
        use_async: bool = True,
        max_concurrency: int | None = None,
    ) -> tuple[list[ChunkResult], AggregatedResult]:
        chunks = self._prepare_chunks(transcript_path, chunk_duration_minutes, overlap_minutes)
        return self.process_chunks(
            lecture_id,
            chunks,
            use_async=use_async,
            max_concurrency=max_concurrency,
        )

    async def process_lecture_async(
        self,
        lecture_id: str,
        transcript_path: str | Path,
        chunk_duration_minutes: int | None = None,
        overlap_minutes: int | None = None,
        max_concurrency: int | None = None,
    ) -> tuple[list[ChunkResult], AggregatedResult]:
        chunks = self._prepare_chunks(transcript_path, chunk_duration_minutes, overlap_minutes)
        return await self.process_chunks_async(
            lecture_id,
            chunks,
            max_concurrency=max_concurrency,
        )

    @staticmethod
    def _atomic_write_json(path: Path, data: Any) -> None:
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

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

        self._atomic_write_json(
            chunk_file,
            [item.model_dump(mode="json") for item in chunk_results],
        )
        self._atomic_write_json(
            aggregated_file,
            aggregated_result.model_dump(mode="json"),
        )
        return chunk_file, aggregated_file

    def run(
        self,
        transcript_path: str | Path,
        output_dir: str | Path | None = None,
        lecture_id: str | None = None,
        chunk_duration_minutes: int | None = None,
        overlap_minutes: int | None = None,
        use_async: bool = True,
        max_concurrency: int | None = None,
    ) -> tuple[list[ChunkResult], AggregatedResult] | tuple[list[ChunkResult], AggregatedResult, Path, Path]:
        resolved_lecture_id = lecture_id or lecture_id_from_transcript_path(transcript_path)
        chunk_results, aggregated_result = self.process_lecture(
            lecture_id=resolved_lecture_id,
            transcript_path=transcript_path,
            chunk_duration_minutes=chunk_duration_minutes,
            overlap_minutes=overlap_minutes,
            use_async=use_async,
            max_concurrency=max_concurrency,
        )

        if output_dir is None:
            return chunk_results, aggregated_result

        chunk_path, aggregated_path = self.save_files(
            chunk_results,
            aggregated_result,
            output_dir,
            resolved_lecture_id,
        )
        return chunk_results, aggregated_result, chunk_path, aggregated_path
