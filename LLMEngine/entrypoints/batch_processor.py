"""여러 강의 스크립트 파일을 배치 처리하는 엔트리포인트."""

from __future__ import annotations

import asyncio
import logging
import sys
from decimal import Decimal

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import time
from pathlib import Path
from typing import Dict

from LLMEngine.core.config import LLMEngineConfig
from LLMEngine.core.logging_config import set_trace_id
from LLMEngine.core.schemas import AggregatedResult
from LLMEngine.application.analyzer_service import (
    LectureAnalyzerService, normalize_lecture_id, get_lecture_id_with_run_number,
)

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
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        batch_t0 = time.perf_counter()

        for file_path in transcript_files:
            path = Path(file_path)
            base_id = normalize_lecture_id(path.stem)
            lecture_id = get_lecture_id_with_run_number(out, base_id)
            file_t0 = time.perf_counter()
            trace_id = set_trace_id()
            logger.info("stage=start file=%s lecture_id=%s trace_id=%s", path.name, lecture_id, trace_id)

            try:
                chunk_results, aggregated = self.service.process_lecture(
                    lecture_id, path, max_concurrency=max_concurrency,
                )
                file_elapsed_ms = int((time.perf_counter() - file_t0) * 1000)
                aggregated.run_metadata.total_elapsed_ms = file_elapsed_ms
                self.service.save_files(chunk_results, aggregated, out, lecture_id)

                meta = aggregated.run_metadata
                logger.info(
                    "stage=done file=%s lecture_id=%s chunks=%d success=%d "
                    "fallback=%d failed=%d elapsed_ms=%d tokens=%d cost=%.6f "
                    "reliability=%.4f",
                    path.name, lecture_id, meta.total_chunks,
                    meta.successful_chunks, meta.fallback_chunks, meta.failed_chunks,
                    file_elapsed_ms,
                    meta.token_usage.total_tokens, meta.token_usage.estimated_cost_usd,
                    meta.reliability.overall_reliability_score,
                )
                results[lecture_id] = {
                    "chunk_results": chunk_results,
                    "aggregated_result": aggregated,
                    "chunk_file": str(out / f"{lecture_id}_chunks.json"),
                    "aggregated_file": str(out / f"{lecture_id}_summary.json"),
                }
            except Exception as exc:
                elapsed = int((time.perf_counter() - file_t0) * 1000)
                msg = f"{type(exc).__name__}: {exc}"
                if hasattr(exc, "__cause__") and exc.__cause__:
                    msg += f" (caused by: {type(exc.__cause__).__name__}: {str(exc.__cause__)[:200]})"
                errors[lecture_id] = msg
                if continue_on_error:
                    logger.error(
                        "stage=error file=%s lecture_id=%s elapsed_ms=%d msg=%s",
                        path.name, lecture_id, elapsed, msg,
                    )
                else:
                    raise RuntimeError(f"처리 실패 {lecture_id}: {msg}") from exc

        total_tokens = 0
        total_cost = Decimal("0")
        for r in results.values():
            agg: AggregatedResult | None = r.get("aggregated_result")
            if agg:
                total_tokens += agg.run_metadata.token_usage.total_tokens
                total_cost += agg.run_metadata.token_usage.estimated_cost_usd

        logger.info(
            "stage=batch_done total=%d success=%d failed=%d elapsed_ms=%d tokens=%d cost=%s",
            len(transcript_files), len(results), len(errors),
            int((time.perf_counter() - batch_t0) * 1000), total_tokens, f"{total_cost:.6f}",
        )
        for lid, msg in errors.items():
            logger.warning("stage=batch_error lecture_id=%s msg=%s", lid, msg)
        return results

    def _resolve_directory(self, target_dir: str | Path) -> Path:
        directory = Path(target_dir).resolve()
        if not directory.exists():
            logger.warning(
                "stage=resolve_directory path=%s 디렉터리가 존재하지 않습니다.", directory,
            )
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
            raise FileNotFoundError(f"'{pattern}' 패턴에 맞는 파일이 없습니다: {directory}")
        if latest_only:
            files = [max(files, key=lambda f: f.stat().st_mtime)]
            logger.info("stage=latest_only file=%s", files[0].name)
        return self.process_files(files, output_dir, continue_on_error, max_concurrency)


if __name__ == "__main__":
    import argparse
    import os
    from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter
    from LLMEngine.infrastructure.persistence.json_repo import LocalJsonRepository

    from LLMEngine.core.logging_config import setup_logging

    use_json = os.getenv("LLM_LOG_FORMAT", "").strip().lower() == "json"
    setup_logging(level=os.getenv("LLM_LOG_LEVEL", "INFO"), json_format=use_json)

    parser = argparse.ArgumentParser(description="강의 스크립트 배치 처리기")
    parser.add_argument("--input", "-i", default="dataset/강의 스크립트")
    parser.add_argument("--output", "-o", default="./output")
    parser.add_argument("--max_concurrency", "-c", type=int, default=1)
    parser.add_argument("--file", "-f", type=str)
    parser.add_argument("--latest", "-l", action="store_true")
    parser.add_argument(
        "--repo", choices=["json", "sqlite"], default="json",
        help="체크포인트 저장소 (json: 파일 기반, sqlite: DB 기반)",
    )
    args = parser.parse_args()

    backend = os.getenv("LLM_BACKEND", "").strip().lower()
    has_gemini = bool(os.getenv("GEMINI_API_KEY", "").strip())
    has_openai = bool(os.getenv("OPENAI_API_KEY", "").strip())

    config = LLMEngineConfig.from_env()

    if backend == "gemini" or (has_gemini and not has_openai):
        from LLMEngine.infrastructure.llm.gemini_adapter import GeminiAdapter
        llm_provider = GeminiAdapter(
            max_retries=config.max_retries,
            retry_base_delay=config.retry_base_delay,
            api_timeout_s=config.api_timeout_s,
            max_completion_tokens=config.max_completion_tokens,
            temperature=config.temperature,
        )
    else:
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
        from LLMEngine.infrastructure.persistence.sqlite_repo import SQLiteRepository
        repository = SQLiteRepository(db_path="./checkpoints.db")
    else:
        repository = LocalJsonRepository()

    service = LectureAnalyzerService(llm_provider, repository, config=config)
    processor = BatchProcessor(service)

    try:
        if args.file:
            fp = Path(args.file).resolve()
            if not fp.exists():
                raise FileNotFoundError(f"파일을 찾을 수 없습니다: {fp}")
            processor.process_files([fp], args.output, max_concurrency=args.max_concurrency)
        else:
            processor.process_directory(
                args.input, args.output,
                max_concurrency=args.max_concurrency, latest_only=args.latest,
            )
    except Exception as e:
        logger.exception("stage=fatal %s: %s", type(e).__name__, e)
    finally:
        if hasattr(llm_provider, "close"):
            try:
                asyncio.run(llm_provider.close())
            except (RuntimeError, Exception):
                pass
