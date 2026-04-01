"""Secret provider abstraction with environment-variable fallback."""

from __future__ import annotations

import abc
import logging
import os

logger = logging.getLogger(__name__)


class SecretProvider(abc.ABC):
    @abc.abstractmethod
    def get(self, key: str) -> str | None:
        """Return a secret value for the given key, or None if unavailable."""

    def get_required(self, key: str) -> str:
        value = self.get(key)
        if value is None:
            raise RuntimeError(f"Required secret '{key}' is missing")
        return value


class EnvSecretProvider(SecretProvider):
    def get(self, key: str) -> str | None:
        return os.getenv(key)


class ChainedSecretProvider(SecretProvider):
    def __init__(self, providers: list[SecretProvider]) -> None:
        self._providers = providers

    def get(self, key: str) -> str | None:
        for provider in self._providers:
            value = provider.get(key)
            if value is not None:
                return value
        return None


_provider: SecretProvider = EnvSecretProvider()


def set_provider(provider: SecretProvider) -> None:
    global _provider
    _provider = provider
    logger.info("Secret provider updated: %s", type(provider).__name__)


def get_secret(key: str) -> str | None:
    return _provider.get(key)


def get_secret_required(key: str) -> str:
    return _provider.get_required(key)
