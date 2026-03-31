"""동시성 모델 테스트 + 경계값/실패 경로 테스트."""

from __future__ import annotations

import asyncio

import pytest

from LLMEngine.application.analyzer_service import LectureAnalyzerService
from LLMEngine.core.config import LLMEngineConfig
from LLMEngine.core.schemas import ChunkStatus
from LLMEngine.tests.conftest import (
    FakeLLMProvider, InMemoryRepository, make_chunk_metadata, make_chunk_result,
)


class TestRunAsyncBatch:
    def test_no_running_loop_uses_asyncio_run(self):
        repo = InMemoryRepository()
        service = LectureAnalyzerService(FakeLLMProvider(), repo)
        chunks = [make_chunk_metadata(chunk_id=i, total_chunks=3) for i in range(1, 4)]
        results, agg = service.process_chunks("batch_lec", chunks, use_async=True)
        assert len(results) == 3
        assert agg.run_metadata.successful_chunks == 3

    def test_fallback_executor_in_running_loop(self):
        from LLMEngine.core.config import NetworkConfig
        repo = InMemoryRepository()
        config = LLMEngineConfig(network=NetworkConfig(api_timeout_s=10.0, max_retries=1))
        service = LectureAnalyzerService(FakeLLMProvider(), repo, config=config)
        chunks = [make_chunk_metadata(chunk_id=1, total_chunks=1)]

        async def _in_loop():
            return service.process_chunks("loop_lec", chunks, use_async=True)

        results, agg = asyncio.run(_in_loop())
        assert len(results) == 1


class TestFailingProvider:
    """LLM 호출이 실패할 때 fallback 동작 검증."""

    def test_sync_failure_produces_fallback(self):
        class FailingProvider(FakeLLMProvider):
            def analyze_chunk(self, chunk):
                raise RuntimeError("API 장애")

        repo = InMemoryRepository()
        service = LectureAnalyzerService(FailingProvider(), repo)
        chunks = [make_chunk_metadata(chunk_id=1, total_chunks=1)]
        results, agg = service.process_chunks("fail_lec", chunks, use_async=False)
        assert len(results) == 1
        assert results[0].is_fallback is True

    def test_async_failure_produces_fallback(self):
        class AsyncFailingProvider(FakeLLMProvider):
            async def analyze_chunk_async(self, chunk):
                raise RuntimeError("async API 장애")

        repo = InMemoryRepository()
        service = LectureAnalyzerService(AsyncFailingProvider(), repo)
        chunks = [make_chunk_metadata(chunk_id=1, total_chunks=1)]
        results, agg = service.process_chunks("afail_lec", chunks, use_async=True)
        assert len(results) == 1
        assert results[0].is_fallback is True


class TestEdgeCasesChunkProcessor:
    """청크 프로세서 경계값 테스트."""

    def test_midnight_wraparound(self, tmp_path):
        from LLMEngine.application.chunk_processor import ChunkProcessor

        f = tmp_path / "midnight.txt"
        lines = [
            "<23:58:00> 강사: 거의 자정입니다.",
            "<23:59:30> 강사: 자정 직전 발화.",
            "<00:01:00> 강사: 자정 이후 발화입니다.",
            "<00:05:00> 강사: 새벽 발화.",
        ]
        f.write_text("\n".join(lines), encoding="utf-8")
        proc = ChunkProcessor()
        chunks = proc.process(f, chunk_duration_minutes=60)
        assert len(chunks) >= 1
        all_text = " ".join(c.text for c in chunks)
        assert "자정 직전" in all_text
        assert "자정 이후" in all_text

    def test_single_line_script(self, tmp_path):
        from LLMEngine.application.chunk_processor import ChunkProcessor

        f = tmp_path / "single.txt"
        f.write_text("<10:00:00> 강사: 유일한 발화", encoding="utf-8")
        proc = ChunkProcessor()
        chunks = proc.process(f)
        assert len(chunks) == 1
        assert chunks[0].chunk_id == 1


class TestEdgeCasesValidation:
    """validation 경계값 테스트."""

    def test_exact_threshold_boundary(self):
        from LLMEngine.application.validation import _compute_similarity

        chunk = "정확히 동일한 텍스트"
        score = _compute_similarity(chunk, chunk)
        assert score == 100.0

    def test_similarity_threshold_80_boundary(self):
        from LLMEngine.application.validation import validate_evidence_quote

        result = validate_evidence_quote("동일 텍스트", "동일 텍스트입니다", similarity_threshold=0.80)
        assert result is True

    def test_very_short_quote_nonmatch(self):
        from LLMEngine.application.validation import validate_evidence_quote

        assert validate_evidence_quote("xyz완전다른내용", "abcdef강의내용입니다") is False

    def test_very_short_quote_substring(self):
        from LLMEngine.application.validation import validate_evidence_quote

        assert validate_evidence_quote("a", "abcdef") is True


class TestEdgeCasesAggregator:
    """집계 경계값 테스트."""

    def test_mixed_fallback_and_success(self):
        from LLMEngine.application.aggregator import ResultAggregator

        provider = FakeLLMProvider()
        agg = ResultAggregator(provider)
        success = make_chunk_result(chunk_id=1, is_fallback=False)
        fallback = make_chunk_result(chunk_id=2, is_fallback=True)
        result = agg.aggregate([success, fallback])
        assert result.run_metadata.scored_chunks == 1
        assert result.run_metadata.fallback_chunks == 1
        assert result.run_metadata.total_chunks == 2

    def test_all_failed_still_aggregates(self):
        from LLMEngine.application.aggregator import ResultAggregator

        provider = FakeLLMProvider()
        agg = ResultAggregator(provider)
        fb1 = make_chunk_result(chunk_id=1, is_fallback=True, status=ChunkStatus.FAILED)
        fb2 = make_chunk_result(chunk_id=2, is_fallback=True, status=ChunkStatus.FAILED)
        result = agg.aggregate([fb1, fb2])
        assert result.run_metadata.total_chunks == 2


class TestEdgeCasesSaveFiles:
    """파일 저장 경계값."""

    def test_save_to_nonexistent_parent(self, tmp_path):
        service = LectureAnalyzerService(FakeLLMProvider(), InMemoryRepository())
        chunks = [make_chunk_metadata(chunk_id=1, total_chunks=1)]
        results, agg = service.process_chunks("save_lec", chunks, use_async=False)
        deep_dir = tmp_path / "a" / "b" / "c"
        cp, sp = service.save_files(results, agg, deep_dir, "save_lec")
        assert cp.exists()
        assert sp.exists()
