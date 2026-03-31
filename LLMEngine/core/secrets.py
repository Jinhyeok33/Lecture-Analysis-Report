"""API 키 및 시크릿 관리 확장 포인트.

기본 구현은 환경 변수에서 키를 읽는다.
운영 배포 시 시크릿 매니저(AWS SSM, HashiCorp Vault, Azure Key Vault 등)를
연동하려면 SecretProvider를 상속하여 구현한 뒤 set_provider()로 교체한다.

사용 예:
    # 기본 (환경 변수)
    key = get_secret("OPENAI_API_KEY")

    # AWS SSM 연동
    set_provider(AWSSSMProvider(region="ap-northeast-2"))
    key = get_secret("OPENAI_API_KEY")
"""

from __future__ import annotations

import abc
import logging
import os

logger = logging.getLogger(__name__)


class SecretProvider(abc.ABC):
    """시크릿 제공자 인터페이스."""

    @abc.abstractmethod
    def get(self, key: str) -> str | None:
        """키 이름으로 시크릿 값을 조회한다. 없으면 None."""

    def get_required(self, key: str) -> str:
        """필수 시크릿. 없으면 RuntimeError."""
        value = self.get(key)
        if value is None:
            raise RuntimeError(f"필수 시크릿 '{key}'를 찾을 수 없습니다.")
        return value


class EnvSecretProvider(SecretProvider):
    """환경 변수 기반 시크릿 제공자 (기본값)."""

    def get(self, key: str) -> str | None:
        return os.getenv(key)


class ChainedSecretProvider(SecretProvider):
    """여러 provider를 순서대로 조회하는 체인 패턴.

    예: ChainedSecretProvider([VaultProvider(), EnvSecretProvider()])
    → Vault에서 먼저 찾고, 없으면 환경 변수에서 조회.
    """

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
    """글로벌 시크릿 프로바이더를 교체한다."""
    global _provider
    _provider = provider
    logger.info("SecretProvider 교체: %s", type(provider).__name__)


def get_secret(key: str) -> str | None:
    """현재 설정된 provider에서 시크릿을 조회한다."""
    return _provider.get(key)


def get_secret_required(key: str) -> str:
    """필수 시크릿을 조회한다. 없으면 RuntimeError."""
    return _provider.get_required(key)
