"""Batch entrypoint for processing one or more lecture transcripts."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Dict

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.common.naming import lecture_id_from_transcript_path, llm_chunks_json_path, llm_json_path
from src.llm_engine.application.analyzer_service import LectureAnalyzerService
from src.llm_engine.core.config import LLMEngineConfig
from src.llm_engine.core.logging_config import set_trace_id
from src.llm_engine.core.schemas import AggregatedResult, ChunkResult

logger = logging.getLogger(__name__)


class BatchProcessor:
    def __init__(self, analyzer_service: LectureAnalyzerService) -> None:
        self.service = analyzer_service

    def process_files(
        self,
        transcript_files: list[str | Path],
        output_dir: str | Path,
        continue_on_error: bool = True,
        max_concurrency: int | None = None,
    ) -> Dict[str, dict]:
        if max_concurrency is None:
            max_concurrency = self.service.config.max_concurrency

        results: Dict[str, dict] = {}
        errors: Dict[str, str] = {}
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        batch_started = time.perf_counter()

        for file_path in transcript_files:
            path = Path(file_path)
            lecture_id = lecture_id_from_transcript_path(path)
            trace_id = set_trace_id()
            file_started = time.perf_counter()

            chunk_file = llm_chunks_json_path(out_path, lecture_id)
            aggregated_file = llm_json_path(out_path, lecture_id)

            logger.info(
                "stage=start file=%s lecture_id=%s trace_id=%s",
                path.name,
                lecture_id,
                trace_id,
            )

            if aggregated_file.exists():
                try:
                    cached_agg = json.loads(aggregated_file.read_text(encoding="utf-8-sig"))
                    cached_chunks: list[ChunkResult] = []
                    if chunk_file.exists():
                        raw_chunks = json.loads(chunk_file.read_text(encoding="utf-8-sig"))
                        cached_chunks = [ChunkResult.model_validate(item) for item in raw_chunks]

                    results[lecture_id] = {
                        "chunk_results": cached_chunks,
                        "aggregated_result": cached_agg,
                        "chunk_file": str(chunk_file),
                        "aggregated_file": str(aggregated_file),
                    }
                    logger.info(
                        "stage=cache_hit file=%s lecture_id=%s aggregated=%s",
                        path.name,
                        lecture_id,
                        aggregated_file.name,
                    )
                    continue
                except Exception as exc:
                    logger.warning(
                        "stage=cache_reload_failed file=%s lecture_id=%s msg=%s",
                        path.name,
                        lecture_id,
                        exc,
                    )

            try:
                chunk_results, aggregated_result = self.service.process_lecture(
                    lecture_id,
                    path,
                    max_concurrency=max_concurrency,
                )

                file_elapsed_ms = int((time.perf_counter() - file_started) * 1000)
                aggregated_result.run_metadata.total_elapsed_ms = file_elapsed_ms
                self.service.save_files(chunk_results, aggregated_result, out_path, lecture_id)

                meta = aggregated_result.run_metadata
                logger.info(
                    "stage=done file=%s lecture_id=%s chunks=%d success=%d fallback=%d failed=%d "
                    "elapsed_ms=%d tokens=%d cost=%s reliability=%.4f",
                    path.name,
                    lecture_id,
                    meta.total_chunks,
                    meta.successful_chunks,
                    meta.fallback_chunks,
                    meta.failed_chunks,
                    file_elapsed_ms,
                    meta.token_usage.total_tokens,
                    str(meta.token_usage.estimated_cost_usd),
                    meta.reliability.overall_reliability_score,
                )

                results[lecture_id] = {
                    "chunk_results": chunk_results,
                    "aggregated_result": aggregated_result,
                    "chunk_file": str(chunk_file),
                    "aggregated_file": str(aggregated_file),
                }
            except Exception as exc:
                elapsed_ms = int((time.perf_counter() - file_started) * 1000)
                message = f"{type(exc).__name__}: {exc}"
                if hasattr(exc, "__cause__") and exc.__cause__:
                    cause = exc.__cause__
                    message += f" (caused by: {type(cause).__name__}: {str(cause)[:200]})"
                errors[lecture_id] = message

                if continue_on_error:
                    logger.error(
                        "stage=error file=%s lecture_id=%s elapsed_ms=%d msg=%s",
                        path.name,
                        lecture_id,
                        elapsed_ms,
                        message,
                    )
                else:
                    raise RuntimeError(f"처리 실패 {lecture_id}: {message}") from exc

        total_tokens = 0
        total_cost = Decimal("0")
        for entry in results.values():
            aggregated = entry.get("aggregated_result")
            if isinstance(aggregated, AggregatedResult):
                total_tokens += aggregated.run_metadata.token_usage.total_tokens
                total_cost += aggregated.run_metadata.token_usage.estimated_cost_usd

        logger.info(
            "stage=batch_done total=%d success=%d failed=%d elapsed_ms=%d tokens=%d cost=%s",
            len(transcript_files),
            len(results),
            len(errors),
            int((time.perf_counter() - batch_started) * 1000),
            total_tokens,
            f"{total_cost:.6f}",
        )
        for lecture_id, message in errors.items():
            logger.warning("stage=batch_error lecture_id=%s msg=%s", lecture_id, message)

        return results

    def _resolve_directory(self, target_dir: str | Path) -> Path:
        directory = Path(target_dir).resolve()
        if directory.exists():
            return directory

        current = Path.cwd()
        while current != current.parent:
            candidate = current / target_dir
            if candidate.exists():
                return candidate.resolve()
            current = current.parent

        logger.warning("stage=resolve_directory_missing path=%s", directory)
        return directory

    def process_directory(
        self,
        transcript_dir: str | Path,
        output_dir: str | Path,
        pattern: str = "*.txt",
        continue_on_error: bool = True,
        max_concurrency: int | None = None,
        latest_only: bool = False,
    ) -> Dict[str, dict]:
        if max_concurrency is None:
            max_concurrency = self.service.config.max_concurrency

        directory = self._resolve_directory(transcript_dir)
        if not directory.exists():
            raise FileNotFoundError(f"스크립트 폴더를 찾을 수 없습니다: {directory}")

        files = sorted(directory.glob(pattern))
        if not files:
            raise FileNotFoundError(f"'{pattern}' 패턴에 맞는 스크립트 파일이 없습니다: {directory}")

        if latest_only:
            files = [max(files, key=lambda path: path.stat().st_mtime)]
            logger.info("stage=latest_only file=%s", files[0].name)

        return self.process_files(
            transcript_files=files,
            output_dir=output_dir,
            continue_on_error=continue_on_error,
            max_concurrency=max_concurrency,
        )


if __name__ == "__main__":
    import argparse

    from src.llm_engine.core.logging_config import setup_logging

    use_json = os.getenv("LLM_LOG_FORMAT", "").strip().lower() == "json"
    setup_logging(level=os.getenv("LLM_LOG_LEVEL", "INFO"), json_format=use_json)

    parser = argparse.ArgumentParser(description="강의 스크립트 배치 처리기")
    parser.add_argument("--input", "-i", type=str, default="data/raw", help="스크립트 폴더 경로")
    parser.add_argument("--output", "-o", type=str, default="data/outputs/llm", help="결과 출력 폴더 경로")
    parser.add_argument("--max_concurrency", "-c", type=int, default=1, help="동시 처리 청크 수")
    parser.add_argument("--file", "-f", type=str, help="특정 파일 하나만 처리할 때 사용할 경로")
    parser.add_argument("--latest", "-l", action="store_true", help="지정 폴더에서 가장 최신 스크립트 1건만 처리")
    parser.add_argument(
        "--repo",
        choices=["json", "sqlite"],
        default="json",
        help="체크포인트 저장소 유형",
    )
    args = parser.parse_args()

    config = LLMEngineConfig.from_env()
    backend = os.getenv("LLM_BACKEND", "").strip().lower()
    has_gemini = bool(os.getenv("GEMINI_API_KEY", "").strip())
    has_openai = bool(os.getenv("OPENAI_API_KEY", "").strip())

    if backend == "gemini" or (has_gemini and not has_openai):
        from src.llm_engine.infrastructure.llm.gemini_adapter import GeminiAdapter

        llm_provider = GeminiAdapter(
            max_retries=config.max_retries,
            retry_base_delay=config.retry_base_delay,
            api_timeout_s=config.api_timeout_s,
            max_completion_tokens=config.max_completion_tokens,
            temperature=config.temperature,
        )
    else:
        from src.llm_engine.infrastructure.llm.openai_adapter import OpenAIAdapter

        llm_provider = OpenAIAdapter(
            model=config.model,
            max_retries=config.max_retries,
            retry_base_delay=config.retry_base_delay,
            api_timeout_s=config.api_timeout_s,
            max_completion_tokens=config.max_completion_tokens,
            temperature=config.temperature,
            seed=config.seed,
        )

    if args.repo == "sqlite":
        from src.llm_engine.infrastructure.persistence.sqlite_repo import SQLiteRepository

        repository = SQLiteRepository(db_path="./checkpoints/checkpoints.db")
    else:
        from src.llm_engine.infrastructure.persistence.json_repo import LocalJsonRepository

        repository = LocalJsonRepository()

    service = LectureAnalyzerService(llm_provider, repository, config=config)
    processor = BatchProcessor(service)

    try:
        if args.file:
            file_path = Path(args.file).resolve()
            if not file_path.exists():
                raise FileNotFoundError(f"지정한 파일을 찾을 수 없습니다: {file_path}")
            processor.process_files([file_path], args.output, max_concurrency=args.max_concurrency)
        else:
            processor.process_directory(
                transcript_dir=args.input,
                output_dir=args.output,
                max_concurrency=args.max_concurrency,
                latest_only=args.latest,
            )
    except Exception as exc:
        logger.exception("stage=fatal %s: %s", type(exc).__name__, exc)
    finally:
        if hasattr(llm_provider, "close"):
            try:
                asyncio.run(llm_provider.close())
            except (RuntimeError, Exception):
                pass
