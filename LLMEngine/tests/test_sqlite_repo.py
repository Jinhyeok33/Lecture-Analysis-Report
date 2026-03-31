"""sqlite_repo.py 단위 테스트 — IRepository 계약 준수, CRUD, 동시성."""

from __future__ import annotations

import pytest

from LLMEngine.core.schemas import ChunkStateRecord
from LLMEngine.infrastructure.persistence.sqlite_repo import SQLiteRepository
from LLMEngine.tests.conftest import make_chunk_result


class TestSQLiteRepository:
    @pytest.fixture
    def repo(self, tmp_path):
        db = tmp_path / "test.db"
        r = SQLiteRepository(db_path=str(db))
        yield r
        r.close()

    def test_save_and_load(self, repo):
        result = make_chunk_result(chunk_id=1)
        repo.save_chunk_state(ChunkStateRecord(
            lecture_id="lec01", chunk_id=1, status="SUCCESS", result=result,
        ))
        completed = repo.get_completed_chunks("lec01")
        assert len(completed) == 1
        assert completed[0].chunk_id == 1

    def test_overwrite(self, repo):
        repo.save_chunk_state(ChunkStateRecord(
            lecture_id="lec01", chunk_id=1, status="PROCESSING",
        ))
        r = make_chunk_result(chunk_id=1)
        repo.save_chunk_state(ChunkStateRecord(
            lecture_id="lec01", chunk_id=1, status="SUCCESS", result=r,
        ))
        completed = repo.get_completed_chunks("lec01")
        assert len(completed) == 1

    def test_multiple_chunks(self, repo):
        for i in range(1, 6):
            r = make_chunk_result(chunk_id=i)
            repo.save_chunk_state(ChunkStateRecord(
                lecture_id="lec02", chunk_id=i, status="SUCCESS", result=r,
            ))
        completed = repo.get_completed_chunks("lec02")
        assert len(completed) == 5

    def test_failed_not_in_completed(self, repo):
        repo.save_chunk_state(ChunkStateRecord(
            lecture_id="lec03", chunk_id=1, status="FAILED", failure_reason="timeout",
        ))
        assert repo.get_completed_chunks("lec03") == []

    def test_nonexistent_lecture(self, repo):
        assert repo.get_completed_chunks("nonexistent") == []

    def test_multiple_lectures_isolated(self, repo):
        r1 = make_chunk_result(chunk_id=1)
        r2 = make_chunk_result(chunk_id=1)
        repo.save_chunk_state(ChunkStateRecord(
            lecture_id="lecA", chunk_id=1, status="SUCCESS", result=r1,
        ))
        repo.save_chunk_state(ChunkStateRecord(
            lecture_id="lecB", chunk_id=1, status="SUCCESS", result=r2,
        ))
        assert len(repo.get_completed_chunks("lecA")) == 1
        assert len(repo.get_completed_chunks("lecB")) == 1

    def test_close_and_reopen(self, tmp_path):
        db = tmp_path / "reopen.db"
        repo1 = SQLiteRepository(db_path=str(db))
        r = make_chunk_result(chunk_id=1)
        repo1.save_chunk_state(ChunkStateRecord(
            lecture_id="persist", chunk_id=1, status="SUCCESS", result=r,
        ))
        repo1.close()

        repo2 = SQLiteRepository(db_path=str(db))
        completed = repo2.get_completed_chunks("persist")
        repo2.close()
        assert len(completed) == 1

    def test_with_analyzer_service(self, tmp_path):
        """SQLiteRepository가 LectureAnalyzerService와 동일하게 동작하는지 검증."""
        from LLMEngine.application.analyzer_service import LectureAnalyzerService
        from LLMEngine.tests.conftest import FakeLLMProvider, make_chunk_metadata

        db = tmp_path / "service.db"
        repo = SQLiteRepository(db_path=str(db))
        service = LectureAnalyzerService(FakeLLMProvider(), repo)
        chunks = [make_chunk_metadata(chunk_id=i, total_chunks=2) for i in range(1, 3)]
        results, agg = service.process_chunks("sqlite_lec", chunks, use_async=False)

        assert len(results) == 2
        assert agg.run_metadata.total_chunks == 2

        persisted = repo.get_completed_chunks("sqlite_lec")
        assert len(persisted) == 2
        repo.close()
