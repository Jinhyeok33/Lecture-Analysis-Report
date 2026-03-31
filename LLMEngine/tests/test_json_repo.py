"""json_repo.py 단위 테스트 — 실제 파일 I/O, atomic write, 손상 복구."""

from __future__ import annotations

import json

import pytest

from LLMEngine.core.schemas import ChunkStateRecord
from LLMEngine.infrastructure.persistence.json_repo import LocalJsonRepository
from LLMEngine.tests.conftest import make_chunk_result


class TestLocalJsonRepository:
    @pytest.fixture
    def repo(self, tmp_path):
        return LocalJsonRepository(base_dir=str(tmp_path))

    def test_save_and_load(self, repo):
        result = make_chunk_result(chunk_id=1)
        repo.save_chunk_state(ChunkStateRecord(
            lecture_id="lec01", chunk_id=1, status="SUCCESS", result=result,
        ))
        completed = repo.get_completed_chunks("lec01")
        assert len(completed) == 1
        assert completed[0].chunk_id == 1

    def test_overwrite_chunk(self, repo):
        r1 = make_chunk_result(chunk_id=1)
        repo.save_chunk_state(ChunkStateRecord(
            lecture_id="lec01", chunk_id=1, status="PROCESSING",
        ))
        repo.save_chunk_state(ChunkStateRecord(
            lecture_id="lec01", chunk_id=1, status="SUCCESS", result=r1,
        ))
        completed = repo.get_completed_chunks("lec01")
        assert len(completed) == 1

    def test_multiple_chunks(self, repo):
        for i in range(1, 4):
            r = make_chunk_result(chunk_id=i)
            repo.save_chunk_state(ChunkStateRecord(
                lecture_id="lec02", chunk_id=i, status="SUCCESS", result=r,
            ))
        completed = repo.get_completed_chunks("lec02")
        assert len(completed) == 3

    def test_failed_chunk_not_in_completed(self, repo):
        repo.save_chunk_state(ChunkStateRecord(
            lecture_id="lec03", chunk_id=1, status="FAILED", failure_reason="timeout",
        ))
        completed = repo.get_completed_chunks("lec03")
        assert len(completed) == 0

    def test_nonexistent_lecture(self, repo):
        completed = repo.get_completed_chunks("nonexistent")
        assert completed == []

    def test_corrupted_file_on_load(self, repo, tmp_path):
        p = tmp_path / "corrupt_checkpoint.json"
        p.write_text("NOT JSON", encoding="utf-8")
        repo.base_dir = tmp_path
        repo._get_path = lambda lid: p
        completed = repo.get_completed_chunks("corrupt")
        assert completed == []

    def test_corrupted_file_on_save(self, repo, tmp_path):
        p = tmp_path / "lec_corrupt_checkpoint.json"
        p.write_text("{broken", encoding="utf-8")
        repo.base_dir = tmp_path

        with pytest.raises(RuntimeError, match="손상"):
            repo.save_chunk_state(ChunkStateRecord(
                lecture_id="lec_corrupt", chunk_id=1, status="PROCESSING",
            ))

    def test_atomic_write_no_tmp_left(self, repo, tmp_path):
        result = make_chunk_result(chunk_id=1)
        repo.save_chunk_state(ChunkStateRecord(
            lecture_id="atomic_test", chunk_id=1, status="SUCCESS", result=result,
        ))
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0
