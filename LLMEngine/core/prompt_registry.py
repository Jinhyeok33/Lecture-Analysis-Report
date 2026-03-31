"""프롬프트 레지스트리 — 외부 YAML 파일 기반 프롬프트 로딩/버전 관리.

YAML 파일이 없으면 코드 내장 프롬프트로 fallback하므로 기존 동작을 깨뜨리지 않는다.
비개발자(교육 전문가)가 프롬프트를 수정하고 A/B 테스트를 수행할 수 있도록 설계.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_yaml(path: Path) -> dict[str, Any]:
    """YAML 파일을 dict로 로딩. pyyaml 미설치 시 빈 dict 반환."""
    if not path.exists():
        return {}
    try:
        import yaml
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except ImportError:
        logger.debug("pyyaml 미설치 — YAML 프롬프트 로딩 건너뜀")
        return {}
    except Exception as e:
        logger.warning("프롬프트 YAML 로딩 실패 (%s): %s", path, e)
        return {}


class PromptRegistry:
    """프롬프트 버전 관리. YAML 외부 파일이 있으면 우선, 없으면 코드 내장 사용."""

    def __init__(self, prompt_dir: Path | str | None = None) -> None:
        self._dir = Path(prompt_dir) if prompt_dir else _PROMPT_DIR
        self._cache: dict[str, dict[str, Any]] = {}

    def _load_version(self, version: str) -> dict[str, Any]:
        if version in self._cache:
            return self._cache[version]
        path = self._dir / f"{version}.yaml"
        data = _load_yaml(path)
        if data:
            logger.info("프롬프트 v%s 로딩: %s", version, path)
        self._cache[version] = data
        return data

    def get_system_prompt(self, version: str, fallback: str) -> str:
        """지정 버전의 system_prompt를 반환. YAML 없으면 fallback 사용."""
        data = self._load_version(version)
        return data.get("system_prompt", fallback)

    def get_aggregator_prompt(self, version: str, fallback: str) -> str:
        data = self._load_version(version)
        return data.get("aggregator_system_prompt", fallback)

    def get_metadata(self, version: str) -> dict[str, Any]:
        """YAML에 포함된 메타데이터(author, description 등) 반환."""
        data = self._load_version(version)
        return {k: v for k, v in data.items() if k not in ("system_prompt", "aggregator_system_prompt")}

    def list_versions(self) -> list[str]:
        """prompts/ 디렉토리 내 사용 가능한 버전 목록."""
        if not self._dir.exists():
            return []
        return sorted(
            p.stem for p in self._dir.glob("*.yaml")
        )

    def clear_cache(self) -> None:
        self._cache.clear()


_default_registry: PromptRegistry | None = None


def get_registry() -> PromptRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = PromptRegistry()
    return _default_registry
