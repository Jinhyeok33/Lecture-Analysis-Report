"""analyzer_service.py 단위 테스트 — FakeLLM + InMemoryRepo로 파이프라인 검증."""

from __future__ import annotations

import json

import pytest

from LLMEngine.core.config import LLMEngineConfig
from LLMEngine.core.schemas import ChunkMetadata, ChunkStatus
from LLMEngine.application.analyzer_service import (
    LectureAnalyzerService, normalize_lecture_id, get_lecture_id_with_run_number,
    _classify_failure_exc,
)
from LLMEngine.core.exceptions import RefusalError, NonRetryableAPIError
from LLMEngine.tests.conftest import (
    FakeLLMProvider, InMemoryRepository, make_chunk_metadata, make_chunk_result,
)


class TestNormalizeLectureId:
    @pytest.mark.parametrize("stem,expected", [
        ("2026-03-02_kdt-backendj-21th", "260302_kdt-backendj-21th"),
        ("my-lecture", "my-lecture"),
        ("2025-01-15", "250115"),
    ])
    def test_cases(self, stem, expected):
        assert normalize_lecture_id(stem) == expected


class TestGetLectureIdWithRunNumber:
    def test_no_existing(self, tmp_path):
        assert get_lecture_id_with_run_number(tmp_path, "lec01") == "lec01_01"

    def test_increment(self, tmp_path):
        (tmp_path / "lec01_01_summary.json").write_text("{}")
        assert get_lecture_id_with_run_number(tmp_path, "lec01") == "lec01_02"

    def test_nonexistent_dir(self, tmp_path):
        fake = tmp_path / "nonexistent"
        assert get_lecture_id_with_run_number(fake, "lec01") == "lec01_01"


class TestClassifyFailureExc:
    def test_refusal(self):
        status, fc = _classify_failure_exc(RefusalError("거부"))
        assert status == ChunkStatus.REFUSED

    def test_non_retryable(self):
        status, fc = _classify_failure_exc(NonRetryableAPIError("quota"))
        assert status == ChunkStatus.FAILED
        assert fc is not None

    def test_timeout(self):
        status, fc = _classify_failure_exc(TimeoutError("timeout"))
        assert status == ChunkStatus.TIMED_OUT

    def test_generic(self):
        status, fc = _classify_failure_exc(RuntimeError("unknown"))
        assert status == ChunkStatus.FAILED

    def test_wrapped_refusal(self):
        cause = RefusalError("inner")
        outer = RuntimeError("재시도 소진")
        outer.__cause__ = cause
        status, _ = _classify_failure_exc(outer)
        assert status == ChunkStatus.REFUSED


class TestEnforceNaPolicy:
    @pytest.fixture
    def service(self):
        return LectureAnalyzerService(FakeLLMProvider(), InMemoryRepository())

    def test_middle_chunk_nullifies_position_items(self, service):
        r = make_chunk_result(chunk_id=2)
        enforced = service._enforce_na_policy(r, total_chunks=3)
        assert enforced.scores.lecture_structure.learning_objective_intro is None
        assert enforced.scores.lecture_structure.previous_lesson_linkage is None
        assert enforced.scores.lecture_structure.closing_summary is None

    def test_first_chunk_keeps_intro(self, service):
        r = make_chunk_result(chunk_id=1)
        enforced = service._enforce_na_policy(r, total_chunks=3)
        assert enforced.scores.lecture_structure.learning_objective_intro is not None
        assert enforced.scores.lecture_structure.closing_summary is None

    def test_last_chunk_keeps_closing(self, service):
        r = make_chunk_result(chunk_id=3)
        enforced = service._enforce_na_policy(r, total_chunks=3)
        assert enforced.scores.lecture_structure.closing_summary is not None
        assert enforced.scores.lecture_structure.learning_objective_intro is None

    def test_single_chunk_keeps_both(self, service):
        r = make_chunk_result(chunk_id=1)
        enforced = service._enforce_na_policy(r, total_chunks=1)
        assert enforced.scores.lecture_structure.learning_objective_intro is not None
        assert enforced.scores.lecture_structure.closing_summary is not None


class TestInjectPreviousChunkTail:
    @pytest.fixture
    def service(self):
        return LectureAnalyzerService(FakeLLMProvider(), InMemoryRepository())

    def test_single_chunk_no_tail(self, service):
        chunks = [make_chunk_metadata(chunk_id=1)]
        result = service._inject_previous_chunk_tail(chunks)
        assert result[0].previous_chunk_tail is None

    def test_second_chunk_gets_tail(self, service):
        c1 = make_chunk_metadata(chunk_id=1, text="첫 번째 청크의 텍스트입니다.\n두번째 줄입니다.")
        c2 = make_chunk_metadata(chunk_id=2)
        result = service._inject_previous_chunk_tail([c1, c2])
        assert result[1].previous_chunk_tail is not None
        assert "첫 번째" in result[1].previous_chunk_tail or "두번째" in result[1].previous_chunk_tail


class TestProcessChunksSync:
    def test_full_pipeline_sync(self):
        repo = InMemoryRepository()
        service = LectureAnalyzerService(FakeLLMProvider(), repo)
        chunks = [make_chunk_metadata(chunk_id=i, total_chunks=2) for i in range(1, 3)]
        results, agg = service.process_chunks("test_lec", chunks, use_async=False)
        assert len(results) == 2
        assert agg.run_metadata.total_chunks == 2
        assert agg.run_metadata.successful_chunks == 2

    def test_checkpoint_resume(self):
        repo = InMemoryRepository()
        provider = FakeLLMProvider()
        service = LectureAnalyzerService(provider, repo)
        chunks = [make_chunk_metadata(chunk_id=i, total_chunks=2) for i in range(1, 3)]

        service.process_chunks("resume_lec", chunks, use_async=False)
        results2, agg2 = service.process_chunks("resume_lec", chunks, use_async=False)
        assert len(results2) == 2


class TestProcessChunksAsync:
    def test_async_pipeline(self):
        import asyncio

        async def _run():
            repo = InMemoryRepository()
            service = LectureAnalyzerService(FakeLLMProvider(), repo)
            chunks = [make_chunk_metadata(chunk_id=i, total_chunks=2) for i in range(1, 3)]
            return await service.process_chunks_async("async_lec", chunks)

        results, agg = asyncio.run(_run())
        assert len(results) == 2


class TestSaveFiles:
    def test_save_and_read(self, tmp_path):
        service = LectureAnalyzerService(FakeLLMProvider(), InMemoryRepository())
        chunks = [make_chunk_metadata(chunk_id=i, total_chunks=2) for i in range(1, 3)]
        results, agg = service.process_chunks("save_lec", chunks, use_async=False)
        cp, sp = service.save_files(results, agg, tmp_path, "save_lec")

        assert cp.exists()
        assert sp.exists()
        chunk_data = json.loads(cp.read_text("utf-8"))
        assert len(chunk_data) == 2
        summary_data = json.loads(sp.read_text("utf-8"))
        assert "run_metadata" in summary_data
