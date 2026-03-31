"""config.py 단위 테스트 — 환경 변수 파싱, 기본값."""

from __future__ import annotations

import os

import pytest

from LLMEngine.core.config import (
    LLMEngineConfig, ChunkConfig, LLMConfig, NetworkConfig,
    _parse_env_optional_int, _parse_env_int, _parse_env_float,
)


class TestParseEnvOptionalInt:
    def test_returns_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("TEST_INT_UNSET", raising=False)
        assert _parse_env_optional_int("TEST_INT_UNSET", 42) == 42

    def test_returns_none_default(self, monkeypatch):
        monkeypatch.delenv("TEST_INT_NONE", raising=False)
        assert _parse_env_optional_int("TEST_INT_NONE", None) is None

    def test_parses_valid(self, monkeypatch):
        monkeypatch.setenv("TEST_INT_VALID", "100")
        assert _parse_env_optional_int("TEST_INT_VALID", 42) == 100

    def test_raises_on_invalid(self, monkeypatch):
        monkeypatch.setenv("TEST_INT_BAD", "abc")
        with pytest.raises(ValueError, match="정수 변환 실패"):
            _parse_env_optional_int("TEST_INT_BAD", 42)


class TestParseEnvInt:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("TEST_REQ_INT", raising=False)
        assert _parse_env_int("TEST_REQ_INT", 5) == 5

    def test_override(self, monkeypatch):
        monkeypatch.setenv("TEST_REQ_INT", "10")
        assert _parse_env_int("TEST_REQ_INT", 5) == 10


class TestParseEnvFloat:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("TEST_FLOAT", raising=False)
        assert _parse_env_float("TEST_FLOAT", 0.5) == 0.5

    def test_override(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "0.7")
        assert _parse_env_float("TEST_FLOAT", 0.5) == 0.7

    def test_invalid(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT_BAD", "not_a_float")
        with pytest.raises(ValueError, match="실수 변환 실패"):
            _parse_env_float("TEST_FLOAT_BAD", 1.0)


class TestLLMEngineConfig:
    def test_defaults(self):
        c = LLMEngineConfig.default()
        assert c.model == "gpt-4o-2024-08-06"
        assert c.seed == 42
        assert c.temperature == 0.5
        assert c.max_concurrency == 1

    def test_from_env_seed_preserved(self, monkeypatch):
        monkeypatch.delenv("LLM_SEED", raising=False)
        c = LLMEngineConfig.from_env()
        assert c.seed == 42

    def test_from_env_seed_override(self, monkeypatch):
        monkeypatch.setenv("LLM_SEED", "123")
        c = LLMEngineConfig.from_env()
        assert c.seed == 123

    def test_from_env_model_override(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "gpt-5")
        c = LLMEngineConfig.from_env()
        assert c.model == "gpt-5"


class TestNestedConfig:
    def test_chunk_config_defaults(self):
        c = LLMEngineConfig.default()
        assert c.chunk.duration_minutes == 12
        assert c.chunk.overlap_minutes == 2
        assert c.chunk_duration_minutes == 12

    def test_llm_config_defaults(self):
        c = LLMEngineConfig.default()
        assert c.llm.model == "gpt-4o-2024-08-06"
        assert c.llm.temperature == 0.5

    def test_network_config_defaults(self):
        c = LLMEngineConfig.default()
        assert c.network.max_retries == 5
        assert c.network.api_timeout_s == 120.0

    def test_custom_nested(self):
        c = LLMEngineConfig(
            chunk=ChunkConfig(duration_minutes=20),
            llm=LLMConfig(temperature=0.8),
            network=NetworkConfig(max_retries=10),
        )
        assert c.chunk_duration_minutes == 20
        assert c.temperature == 0.8
        assert c.max_retries == 10

    def test_from_env_nested(self, monkeypatch):
        monkeypatch.setenv("LLM_CHUNK_DURATION_MINUTES", "30")
        monkeypatch.setenv("LLM_TEMPERATURE", "0.9")
        monkeypatch.setenv("LLM_MAX_RETRIES", "7")
        c = LLMEngineConfig.from_env()
        assert c.chunk.duration_minutes == 30
        assert c.llm.temperature == 0.9
        assert c.network.max_retries == 7


class TestConfigImmutability:
    def test_frozen_chunk_config(self):
        c = ChunkConfig()
        with pytest.raises(AttributeError):
            c.duration_minutes = 99  # type: ignore[misc]

    def test_frozen_llm_config(self):
        c = LLMConfig()
        with pytest.raises(AttributeError):
            c.model = "new-model"  # type: ignore[misc]

    def test_frozen_network_config(self):
        c = NetworkConfig()
        with pytest.raises(AttributeError):
            c.max_retries = 99  # type: ignore[misc]

    def test_frozen_engine_config(self):
        c = LLMEngineConfig.default()
        with pytest.raises(AttributeError):
            c.chunk = ChunkConfig(duration_minutes=99)  # type: ignore[misc]
