"""secrets.py 단위 테스트."""

from __future__ import annotations

import pytest

from LLMEngine.core.secrets import (
    SecretProvider, EnvSecretProvider, ChainedSecretProvider,
    get_secret, get_secret_required, set_provider,
)


class TestEnvSecretProvider:
    def test_returns_env_value(self, monkeypatch):
        monkeypatch.setenv("TEST_SECRET", "my_secret")
        provider = EnvSecretProvider()
        assert provider.get("TEST_SECRET") == "my_secret"

    def test_returns_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("TEST_SECRET_MISSING", raising=False)
        provider = EnvSecretProvider()
        assert provider.get("TEST_SECRET_MISSING") is None

    def test_get_required_raises(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        provider = EnvSecretProvider()
        with pytest.raises(RuntimeError, match="필수 시크릿"):
            provider.get_required("MISSING_KEY")


class InMemoryProvider(SecretProvider):
    def __init__(self, data: dict[str, str]):
        self._data = data

    def get(self, key: str) -> str | None:
        return self._data.get(key)


class TestChainedSecretProvider:
    def test_first_provider_wins(self):
        p1 = InMemoryProvider({"KEY": "from_p1"})
        p2 = InMemoryProvider({"KEY": "from_p2"})
        chain = ChainedSecretProvider([p1, p2])
        assert chain.get("KEY") == "from_p1"

    def test_fallback_to_second(self):
        p1 = InMemoryProvider({})
        p2 = InMemoryProvider({"KEY": "from_p2"})
        chain = ChainedSecretProvider([p1, p2])
        assert chain.get("KEY") == "from_p2"

    def test_none_when_all_miss(self):
        chain = ChainedSecretProvider([InMemoryProvider({})])
        assert chain.get("MISSING") is None


class TestGlobalAPI:
    def test_set_and_get(self, monkeypatch):
        custom = InMemoryProvider({"CUSTOM_KEY": "custom_value"})
        set_provider(custom)
        assert get_secret("CUSTOM_KEY") == "custom_value"
        set_provider(EnvSecretProvider())

    def test_get_required_success(self, monkeypatch):
        monkeypatch.setenv("REQUIRED_KEY", "val")
        set_provider(EnvSecretProvider())
        assert get_secret_required("REQUIRED_KEY") == "val"

    def test_get_required_failure(self, monkeypatch):
        monkeypatch.delenv("NOPE", raising=False)
        set_provider(EnvSecretProvider())
        with pytest.raises(RuntimeError):
            get_secret_required("NOPE")
