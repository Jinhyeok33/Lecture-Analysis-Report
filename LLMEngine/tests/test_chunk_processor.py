"""chunk_processor 단위 테스트 — 파싱, 청크 분할, 경계 케이스."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from LLMEngine.application.chunk_processor import ChunkProcessor


@pytest.fixture
def processor():
    return ChunkProcessor()


class TestParseScriptFile:
    def test_normal_format(self, processor, mock_script_path):
        result = processor.parse_script_file(mock_script_path)
        assert len(result.lines) > 0
        assert result.parse_failure_count == 0
        assert result.lines[0].timestamp == "09:11:04"

    def test_strict_parse_raises_on_bad_line(self, processor, tmp_path):
        bad_file = tmp_path / "bad.txt"
        bad_file.write_text(
            "<00:00:01> 강사: 정상 라인\n이건 포맷이 깨진 라인\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="포맷 불일치"):
            processor.parse_script_file(bad_file, strict_parse=True)

    def test_lenient_parse_merges_bad_lines(self, processor, tmp_path):
        f = tmp_path / "lenient.txt"
        f.write_text(
            "<00:00:01> 강사: 첫번째 라인\n이어지는 텍스트\n<00:00:10> 강사: 두번째\n",
            encoding="utf-8",
        )
        result = processor.parse_script_file(f, strict_parse=False)
        assert result.parse_failure_count == 1
        assert "이어지는 텍스트" in result.lines[0].text

    def test_empty_file_raises(self, processor, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="최소 한 줄"):
            processor.parse_script_file(f)

    def test_first_line_fallback(self, processor, tmp_path):
        f = tmp_path / "no_ts.txt"
        f.write_text("포맷 없는 첫 줄\n<00:00:10> 강사: 두번째\n", encoding="utf-8")
        result = processor.parse_script_file(f)
        assert result.lines[0].timestamp == "00:00:00"
        assert result.lines[0].speaker_id == "화자미상"


class TestCreateTimeBasedChunks:
    def test_mock_data_produces_single_chunk(self, processor, mock_script_path):
        parsed = processor.parse_script_file(mock_script_path)
        chunks = processor.create_time_based_chunks(parsed, chunk_duration_minutes=60)
        assert len(chunks) == 1
        assert chunks[0].chunk_id == 1
        assert chunks[0].word_count > 0

    def test_short_chunk_duration(self, processor, mock_script_path):
        parsed = processor.parse_script_file(mock_script_path)
        chunks = processor.create_time_based_chunks(parsed, chunk_duration_minutes=1, overlap_minutes=0)
        assert len(chunks) >= 1

    def test_invalid_duration_raises(self, processor, mock_script_path):
        parsed = processor.parse_script_file(mock_script_path)
        with pytest.raises(ValueError):
            processor.create_time_based_chunks(parsed, chunk_duration_minutes=0)

    def test_overlap_ge_duration_raises(self, processor, mock_script_path):
        parsed = processor.parse_script_file(mock_script_path)
        with pytest.raises(ValueError):
            processor.create_time_based_chunks(parsed, chunk_duration_minutes=5, overlap_minutes=5)

    def test_process_shortcut(self, processor, mock_script_path):
        chunks = processor.process(mock_script_path, chunk_duration_minutes=60)
        assert len(chunks) >= 1
        assert chunks[0].text
