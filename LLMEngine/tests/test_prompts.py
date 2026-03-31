"""prompts.py 단위 테스트 — 프롬프트 생성, 위치 힌트 로직."""

from __future__ import annotations

import pytest

from LLMEngine.core.schemas import ChunkMetadata
from LLMEngine.application.prompts import build_user_prompt, SYSTEM_PROMPT, PROMPT_VERSION


def _make_chunk(chunk_id: int = 1, total: int = 3, text: str = "강사: 테스트 발화") -> ChunkMetadata:
    return ChunkMetadata(
        chunk_id=chunk_id, start_time="00:00", end_time="00:10",
        text=text, line_count=1, word_count=3, total_chunks=total,
    )


class TestBuildUserPrompt:
    def test_contains_text(self):
        prompt = build_user_prompt(_make_chunk(text="강사: 오늘의 주제는 IO입니다"), total_chunks=3)
        assert "오늘의 주제는 IO입니다" in prompt

    def test_first_chunk_hint(self):
        prompt = build_user_prompt(_make_chunk(chunk_id=1, total=3), total_chunks=3)
        assert "첫 번째" in prompt

    def test_last_chunk_hint(self):
        prompt = build_user_prompt(_make_chunk(chunk_id=3, total=3), total_chunks=3)
        assert "마지막" in prompt

    def test_single_chunk_has_both_hints(self):
        prompt = build_user_prompt(_make_chunk(chunk_id=1, total=1), total_chunks=1)
        assert "첫 번째" in prompt
        assert "마지막" in prompt

    def test_middle_chunk_no_position_hint(self):
        prompt = build_user_prompt(_make_chunk(chunk_id=2, total=3), total_chunks=3)
        assert "첫 번째" not in prompt
        assert "마지막" not in prompt

    def test_previous_chunk_tail_injected(self):
        c = _make_chunk()
        c = c.model_copy(update={"previous_chunk_tail": "이전 청크의 마지막 내용"})
        prompt = build_user_prompt(c)
        assert "이전 청크" in prompt

    def test_system_prompt_is_korean(self):
        assert "한국어" in SYSTEM_PROMPT

    def test_prompt_version_exists(self):
        assert PROMPT_VERSION
        assert PROMPT_VERSION.startswith("v")
