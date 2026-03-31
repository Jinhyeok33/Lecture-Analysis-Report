"""End-to-end 통합 테스트.

FakeLLMProvider + InMemoryRepository를 사용하여
batch_processor → analyzer_service → aggregator 전체 파이프라인을 검증한다.
LLM API 호출 없이 실행된다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from LLMEngine.application.analyzer_service import LectureAnalyzerService
from LLMEngine.core.config import LLMEngineConfig, NetworkConfig
from LLMEngine.entrypoints.batch_processor import BatchProcessor
from LLMEngine.tests.conftest import (
    FakeLLMProvider, InMemoryRepository, MOCK_SCRIPT_PATH,
)


@pytest.fixture
def mock_transcript(tmp_path: Path) -> Path:
    """최소 크기 테스트용 스크립트 파일."""
    f = tmp_path / "test_lecture.txt"
    lines = [
        "<10:00:00> 강사: 오늘은 파이썬 기초를 배워보겠습니다. 학습 목표는 변수와 자료형입니다.",
        "<10:03:00> 강사: 변수란 데이터를 저장하는 공간입니다. 예를 들어 x = 10이라고 하면 x에 10이 저장됩니다.",
        "<10:06:00> 강사: 자료형에는 정수, 실수, 문자열 등이 있습니다.",
        "<10:09:00> 강사: 정수는 int, 실수는 float이라고 합니다.",
        "<10:12:00> 강사: 실습으로 넘어가겠습니다. 직접 변수를 선언해보세요.",
        "<10:15:00> 강사: 잘 하셨습니다. 오늘 배운 내용을 정리하면 변수와 자료형의 기초입니다.",
    ]
    f.write_text("\n".join(lines), encoding="utf-8")
    return f


class TestEndToEndPipeline:
    """batch_processor를 통한 전체 파이프라인 검증."""

    def test_single_file_processing(self, mock_transcript: Path, tmp_path: Path):
        output_dir = tmp_path / "output"
        config = LLMEngineConfig(network=NetworkConfig(max_concurrency=1))
        repo = InMemoryRepository()
        provider = FakeLLMProvider()

        with LectureAnalyzerService(provider, repo, config=config) as service:
            processor = BatchProcessor(service)
            results = processor.process_files(
                [mock_transcript], output_dir, continue_on_error=False,
            )

        assert len(results) == 1
        lecture_id = list(results.keys())[0]

        chunks_file = Path(results[lecture_id]["chunk_file"])
        summary_file = Path(results[lecture_id]["aggregated_file"])
        assert chunks_file.exists()
        assert summary_file.exists()

        chunk_data = json.loads(chunks_file.read_text("utf-8"))
        assert isinstance(chunk_data, list)
        assert len(chunk_data) >= 1

        summary_data = json.loads(summary_file.read_text("utf-8"))
        assert "run_metadata" in summary_data
        assert "llm_aggregated_analysis" in summary_data

        meta = summary_data["run_metadata"]
        assert meta["total_chunks"] >= 1
        assert meta["successful_chunks"] >= 1
        assert meta["fallback_chunks"] == 0

    def test_multiple_files(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        scripts = []
        for i in range(3):
            f = tmp_path / f"lecture_{i}.txt"
            f.write_text(
                f"<10:00:00> 강사: 강의 {i}번 내용입니다.\n"
                f"<10:05:00> 강사: 추가 설명입니다.\n",
                encoding="utf-8",
            )
            scripts.append(f)

        repo = InMemoryRepository()
        with LectureAnalyzerService(FakeLLMProvider(), repo) as service:
            processor = BatchProcessor(service)
            results = processor.process_files(scripts, output_dir)

        assert len(results) == 3

    def test_error_recovery(self, mock_transcript: Path, tmp_path: Path):
        """하나의 파일 처리가 실패해도 continue_on_error=True면 계속 진행."""
        bad_file = tmp_path / "nonexistent.txt"
        output_dir = tmp_path / "output"

        repo = InMemoryRepository()
        with LectureAnalyzerService(FakeLLMProvider(), repo) as service:
            processor = BatchProcessor(service)
            results = processor.process_files(
                [bad_file, mock_transcript], output_dir, continue_on_error=True,
            )

        assert len(results) >= 1


class TestEndToEndAsync:
    """비동기 경로 검증."""

    def test_async_processing(self, mock_transcript: Path, tmp_path: Path):
        import asyncio

        async def _run():
            repo = InMemoryRepository()
            config = LLMEngineConfig(network=NetworkConfig(max_concurrency=2))
            service = LectureAnalyzerService(FakeLLMProvider(), repo, config=config)
            chunks = service._prepare_chunks(mock_transcript, None, None)
            return await service.process_chunks_async("async_e2e", chunks)

        results, agg = asyncio.run(_run())
        assert len(results) >= 1
        assert agg.run_metadata.total_chunks == len(results)


class TestEndToEndWithMockData:
    """실제 mock 데이터 파일을 사용한 통합 테스트."""

    @pytest.mark.skipif(
        not MOCK_SCRIPT_PATH.exists(),
        reason=f"mock 데이터 없음: {MOCK_SCRIPT_PATH}",
    )
    def test_full_mock_processing(self, tmp_path: Path):
        output_dir = tmp_path / "output"
        repo = InMemoryRepository()

        with LectureAnalyzerService(FakeLLMProvider(), repo) as service:
            processor = BatchProcessor(service)
            results = processor.process_files(
                [MOCK_SCRIPT_PATH], output_dir, continue_on_error=False,
            )

        assert len(results) == 1
        lid = list(results.keys())[0]
        summary = json.loads(Path(results[lid]["aggregated_file"]).read_text("utf-8"))
        meta = summary["run_metadata"]
        assert meta["total_chunks"] >= 1
        assert meta["successful_chunks"] == meta["total_chunks"]


class TestContextManagerCleanup:
    """서비스 리소스 정리 검증."""

    def test_close_called(self):
        repo = InMemoryRepository()
        service = LectureAnalyzerService(FakeLLMProvider(), repo)
        assert service._closed is False
        service.close()
        assert service._closed is True

    def test_context_manager_closes(self):
        repo = InMemoryRepository()
        with LectureAnalyzerService(FakeLLMProvider(), repo) as service:
            assert service._closed is False
        assert service._closed is True

    def test_double_close_safe(self):
        repo = InMemoryRepository()
        service = LectureAnalyzerService(FakeLLMProvider(), repo)
        service.close()
        service.close()
        assert service._closed is True
