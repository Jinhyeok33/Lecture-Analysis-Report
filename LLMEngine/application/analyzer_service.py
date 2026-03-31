"""강의 스크립트 분석 파이프라인 (오케스트레이터)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from LLMEngine.core.config import LLMEngineConfig
from LLMEngine.core.ports import ILLMProvider, IRepository
from LLMEngine.core.schemas import (
    AggregatedResult, ChunkMetadata, ChunkResult, ChunkScores, ChunkStatus,
    FailureClass, ChunkStateRecord, LectureStructureScores,
    ConceptClarityScores, PracticeLinkageScores, InteractionScores,
    ReliabilityMetrics, PREVIOUS_CHUNK_TAIL_MAX_CHARS,
)
from LLMEngine.application.chunk_processor import ChunkProcessor
from LLMEngine.application.aggregator import ResultAggregator
from LLMEngine.core.exceptions import RefusalError, NonRetryableAPIError

logger = logging.getLogger(__name__)

NA_FIRST_CHUNK_ONLY = frozenset({"learning_objective_intro", "previous_lesson_linkage"})
NA_LAST_CHUNK_ONLY = frozenset({"closing_summary"})


# ── 유틸리티 (batch_processor에서도 import) ──────────────────────────

def normalize_lecture_id(stem: str) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(.*)$", stem)
    if m:
        return f"{m.group(1)[2:]}{m.group(2)}{m.group(3)}{m.group(4)}"
    return stem


def get_lecture_id_with_run_number(output_dir: Path, base_lecture_id: str) -> str:
    if not output_dir.exists():
        return f"{base_lecture_id}_01"
    prefix = f"{base_lecture_id}_"
    run_numbers: list[int] = []
    for p in output_dir.iterdir():
        if not p.is_file() or not p.name.endswith("_summary.json"):
            continue
        name = p.stem
        if name.startswith(prefix):
            num_part = name[len(prefix):].split("_")[0]
            if num_part.isdigit():
                run_numbers.append(int(num_part))
        elif name == f"{base_lecture_id}_summary":
            run_numbers.append(1)
    if not run_numbers:
        return f"{base_lecture_id}_01"
    return f"{base_lecture_id}_{max(run_numbers) + 1:02d}"


def _classify_failure_exc(exc: BaseException) -> tuple[ChunkStatus, FailureClass | None]:
    """예외 타입을 기반으로 ChunkStatus/FailureClass를 분류한다."""
    if isinstance(exc, RefusalError):
        return ChunkStatus.REFUSED, None
    if isinstance(exc, NonRetryableAPIError):
        return ChunkStatus.FAILED, FailureClass.NON_RETRYABLE
    if isinstance(exc, TimeoutError):
        return ChunkStatus.TIMED_OUT, FailureClass.RETRYABLE
    # RuntimeError wrapping (재시도 소진 등)은 cause 를 확인
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        if isinstance(cause, RefusalError):
            return ChunkStatus.REFUSED, None
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
        self._fallback_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="async_fallback")
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._repo_executor.shutdown(wait=False)
        self._fallback_executor.shutdown(wait=False)

    def __enter__(self) -> LectureAnalyzerService:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── 전처리 ───────────────────────────────────────────────────────

    @staticmethod
    def _inject_previous_chunk_tail(chunks: list[ChunkMetadata]) -> list[ChunkMetadata]:
        if len(chunks) <= 1:
            return list(chunks)
        out: list[ChunkMetadata] = [chunks[0]]
        for i in range(1, len(chunks)):
            raw_tail = chunks[i - 1].text[-PREVIOUS_CHUNK_TAIL_MAX_CHARS:]
            newline_pos = raw_tail.find("\n")
            tail = raw_tail[newline_pos + 1:] if newline_pos >= 0 else raw_tail
            out.append(chunks[i].model_copy(update={"previous_chunk_tail": tail or None}))
        return out

    @staticmethod
    def _enforce_na_policy(result: ChunkResult, total_chunks: int) -> ChunkResult:
        """위치 의존 항목: 해당 위치가 아니면 null 강제."""
        is_first = result.chunk_id == 1
        is_last = result.chunk_id == total_chunks
        scores = result.scores.model_dump()
        ls = scores["lecture_structure"]
        changed = False

        if not is_first:
            for key in NA_FIRST_CHUNK_ONLY:
                if ls.get(key) is not None:
                    ls[key] = None
                    changed = True
        if not is_last:
            for key in NA_LAST_CHUNK_ONLY:
                if ls.get(key) is not None:
                    ls[key] = None
                    changed = True

        if not changed:
            return result
        return result.model_copy(update={"scores": ChunkScores.model_validate(scores)})

    def _get_fallback_result(
        self,
        chunk: ChunkMetadata,
        failure_reason: str = "알 수 없는 오류",
        status: ChunkStatus = ChunkStatus.FAILED,
        failure_class: FailureClass | None = FailureClass.RETRYABLE,
        retry_count: int = 0,
    ) -> ChunkResult:
        return ChunkResult(
            chunk_id=chunk.chunk_id,
            start_time=chunk.start_time, end_time=chunk.end_time,
            scores=ChunkScores(
                lecture_structure=LectureStructureScores(
                    learning_objective_intro=None, previous_lesson_linkage=None,
                    explanation_sequence=3, key_point_emphasis=3, closing_summary=None,
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
            ),
            strengths=["분석 실패로 인한 기본값"],
            issues=["분석 실패로 인한 기본값"],
            evidence=[],
            status=status, failure_class=failure_class,
            is_fallback=True, failure_reason=failure_reason, retry_count=retry_count,
            reliability=ReliabilityMetrics(
                evidence_pass_ratio=0.0, hallucination_retries=0,
                avg_evidence_similarity=0.0, score_evidence_consistency=0.0,
                overall_reliability_score=0.0,
            ),
        )

    # ── 공통 에러 → fallback ─────────────────────────────────────────

    def _failure_to_fallback(
        self, chunk: ChunkMetadata, exc: BaseException, lecture_id: str,
    ) -> ChunkResult:
        """예외를 분류하고 fallback 결과를 생성한다. 로깅 포함."""
        error_str = str(exc) or type(exc).__name__
        status, fc = _classify_failure_exc(exc)
        logger.error("lecture_id=%s chunk_id=%d %s: %s",
                     lecture_id, chunk.chunk_id, type(exc).__name__, error_str)
        return self._get_fallback_result(
            chunk, failure_reason=error_str, status=status, failure_class=fc,
        )

    # ── 체크포인트 공통 로직 ────────────────────────────────────────

    def _resume_checkpoint(
        self, lecture_id: str, chunks: list[ChunkMetadata],
    ) -> tuple[dict[int, ChunkResult], list[ChunkMetadata]]:
        completed = self.repo.get_completed_chunks(lecture_id)
        results_map = {c.chunk_id: c for c in completed}
        pending = [c for c in chunks if c.chunk_id not in results_map]
        return results_map, pending

    def _finalize(
        self, chunks: list[ChunkMetadata], results_map: dict[int, ChunkResult],
    ) -> tuple[list[ChunkResult], AggregatedResult]:
        total = len(chunks)
        final = [
            self._enforce_na_policy(results_map[c.chunk_id], total)
            for c in chunks if c.chunk_id in results_map
        ]
        return final, self.aggregator.aggregate(final)

    # ── 동기 처리 ────────────────────────────────────────────────────

    def _run_async_batch(
        self, lecture_id: str, pending: list[ChunkMetadata], max_concurrency: int,
    ) -> list[ChunkResult]:
        """async 청크 배치를 sync 컨텍스트에서 실행한다."""
        coro = self._process_chunks_async(lecture_id, pending, max_concurrency)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            timeout = self.config.api_timeout_s * len(pending) * (self.config.max_retries + 1)
            return self._fallback_executor.submit(asyncio.run, coro).result(timeout=timeout)
        return asyncio.run(coro)

    def process_chunks(
        self,
        lecture_id: str,
        chunks: list[ChunkMetadata],
        use_async: bool = True,
        max_concurrency: int | None = None,
    ) -> tuple[list[ChunkResult], AggregatedResult]:
        if max_concurrency is None:
            max_concurrency = self.config.max_concurrency
        results_map, pending = self._resume_checkpoint(lecture_id, chunks)

        if pending:
            if use_async:
                logger.info("lecture_id=%s stage=batch pending=%d concurrency=%d",
                            lecture_id, len(pending), max_concurrency)
                for r in self._run_async_batch(lecture_id, pending, max_concurrency):
                    results_map[r.chunk_id] = r
            else:
                logger.info("lecture_id=%s stage=batch_sync pending=%d", lecture_id, len(pending))
                for chunk in pending:
                    self.repo.save_chunk_state(ChunkStateRecord(
                        lecture_id=lecture_id, chunk_id=chunk.chunk_id, status="PROCESSING",
                    ))
                    try:
                        res = self.llm.analyze_chunk(chunk)
                        self.repo.save_chunk_state(ChunkStateRecord(
                            lecture_id=lecture_id, chunk_id=chunk.chunk_id,
                            status="SUCCESS", result=res,
                        ))
                        results_map[chunk.chunk_id] = res
                    except Exception as e:
                        self.repo.save_chunk_state(ChunkStateRecord(
                            lecture_id=lecture_id, chunk_id=chunk.chunk_id,
                            status="FAILED", failure_reason=str(e),
                        ))
                        results_map[chunk.chunk_id] = self._failure_to_fallback(chunk, e, lecture_id)

        return self._finalize(chunks, results_map)

    # ── 비동기 처리 ──────────────────────────────────────────────────

    async def _process_chunks_async(
        self, lecture_id: str, chunks: list[ChunkMetadata], max_concurrency: int,
    ) -> list[ChunkResult]:
        sem = asyncio.Semaphore(max_concurrency)
        loop = asyncio.get_running_loop()

        async def _save(record: ChunkStateRecord) -> None:
            await loop.run_in_executor(self._repo_executor, self.repo.save_chunk_state, record)

        async def analyze_one(chunk: ChunkMetadata) -> ChunkResult:
            async with sem:
                await _save(ChunkStateRecord(
                    lecture_id=lecture_id, chunk_id=chunk.chunk_id, status="PROCESSING",
                ))
                try:
                    res = await self.llm.analyze_chunk_async(chunk)
                    await _save(ChunkStateRecord(
                        lecture_id=lecture_id, chunk_id=chunk.chunk_id,
                        status="SUCCESS", result=res,
                    ))
                    return res
                except asyncio.CancelledError:
                    await _save(ChunkStateRecord(
                        lecture_id=lecture_id, chunk_id=chunk.chunk_id,
                        status="FAILED", failure_reason="CancelledError",
                    ))
                    raise
                except Exception as e:
                    await _save(ChunkStateRecord(
                        lecture_id=lecture_id, chunk_id=chunk.chunk_id,
                        status="FAILED", failure_reason=str(e),
                    ))
                    return self._failure_to_fallback(chunk, e, lecture_id)

        raw = await asyncio.gather(*[analyze_one(c) for c in chunks], return_exceptions=True)

        for r in raw:
            if isinstance(r, asyncio.CancelledError):
                raise asyncio.CancelledError()

        return [
            self._failure_to_fallback(chunk, r, lecture_id) if isinstance(r, BaseException) else r
            for chunk, r in zip(chunks, raw)
        ]

    # ── Public async API ─────────────────────────────────────────────

    async def process_chunks_async(
        self, lecture_id: str, chunks: list[ChunkMetadata], max_concurrency: int | None = None,
    ) -> tuple[list[ChunkResult], AggregatedResult]:
        if max_concurrency is None:
            max_concurrency = self.config.max_concurrency
        results_map, pending = self._resume_checkpoint(lecture_id, chunks)

        if pending:
            logger.info("lecture_id=%s stage=batch_async pending=%d concurrency=%d",
                        lecture_id, len(pending), max_concurrency)
            for r in await self._process_chunks_async(lecture_id, pending, max_concurrency):
                results_map[r.chunk_id] = r

        return self._finalize(chunks, results_map)

    # ── 강의 단위 처리 ──────────────────────────────────────────────

    def _prepare_chunks(
        self, path: str | Path, duration: int | None, overlap: int | None,
    ) -> list[ChunkMetadata]:
        d = duration or self.config.chunk_duration_minutes
        o = overlap if overlap is not None else self.config.overlap_minutes
        raw = self.chunker.process(path, chunk_duration_minutes=d, overlap_minutes=o)
        total = len(raw)
        raw = [c.model_copy(update={"total_chunks": total}) for c in raw]
        return self._inject_previous_chunk_tail(raw)

    def process_lecture(
        self, lecture_id: str, transcript_path: str | Path,
        chunk_duration_minutes: int | None = None, overlap_minutes: int | None = None,
        use_async: bool = True, max_concurrency: int | None = None,
    ) -> tuple[list[ChunkResult], AggregatedResult]:
        chunks = self._prepare_chunks(transcript_path, chunk_duration_minutes, overlap_minutes)
        return self.process_chunks(lecture_id, chunks, use_async=use_async, max_concurrency=max_concurrency)

    async def process_lecture_async(
        self, lecture_id: str, transcript_path: str | Path,
        chunk_duration_minutes: int | None = None, overlap_minutes: int | None = None,
        max_concurrency: int | None = None,
    ) -> tuple[list[ChunkResult], AggregatedResult]:
        chunks = self._prepare_chunks(transcript_path, chunk_duration_minutes, overlap_minutes)
        return await self.process_chunks_async(lecture_id, chunks, max_concurrency=max_concurrency)

    # ── 파일 저장 ────────────────────────────────────────────────────

    @staticmethod
    def _atomic_write_json(path: Path, data: Any) -> None:
        """tmp → rename 패턴으로 atomic write."""
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(path)
        except Exception:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise

    def save_files(
        self, chunk_results: list[ChunkResult], aggregated: AggregatedResult,
        output_dir: str | Path, lecture_id: str,
    ) -> tuple[Path, Path]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        chunks_path = out / f"{lecture_id}_chunks.json"
        summary_path = out / f"{lecture_id}_summary.json"

        self._atomic_write_json(chunks_path, [c.model_dump(mode="json") for c in chunk_results])
        self._atomic_write_json(summary_path, aggregated.model_dump(mode="json"))
        return chunks_path, summary_path

    def run(
        self, transcript_path: str | Path, output_dir: str | Path | None = None,
        lecture_id: str | None = None,
        chunk_duration_minutes: int | None = None, overlap_minutes: int | None = None,
        use_async: bool = True, max_concurrency: int | None = None,
    ) -> tuple[list[ChunkResult], AggregatedResult, Path | None, Path | None]:
        base_id = lecture_id or normalize_lecture_id(Path(transcript_path).stem)
        lid = get_lecture_id_with_run_number(Path(output_dir), base_id) if output_dir else base_id

        results, aggregated = self.process_lecture(
            lid, transcript_path,
            chunk_duration_minutes=chunk_duration_minutes, overlap_minutes=overlap_minutes,
            use_async=use_async, max_concurrency=max_concurrency,
        )
        if output_dir is None:
            return results, aggregated, None, None
        chunk_path, agg_path = self.save_files(results, aggregated, output_dir, lid)
        return results, aggregated, chunk_path, agg_path
