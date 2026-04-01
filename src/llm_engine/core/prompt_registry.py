"""Prompt registry with YAML-backed fallback loading."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a prompt YAML if available; otherwise return an empty mapping."""
    if not path.exists():
        return {}
    try:
        import yaml

        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        return data if isinstance(data, dict) else {}
    except ImportError:
        logger.debug("pyyaml not installed; skipping YAML prompt loading")
        return {}
    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.warning("Failed to load prompt YAML (%s): %s", path, exc)
        return {}


class PromptRegistry:
    """Resolve prompt versions from YAML first, then fall back to built-ins."""

    def __init__(self, prompt_dir: Path | str | None = None) -> None:
        self._dir = Path(prompt_dir) if prompt_dir else _PROMPT_DIR
        self._cache: dict[str, dict[str, Any]] = {}

    def _load_version(self, version: str) -> dict[str, Any]:
        if version in self._cache:
            return self._cache[version]

        path = self._dir / f"{version}.yaml"
        data = _load_yaml(path)
        if data:
            logger.info("Loaded prompt version %s from %s", version, path)
        self._cache[version] = data
        return data

    def get_system_prompt(self, version: str, fallback: str) -> str:
        data = self._load_version(version)
        return data.get("system_prompt", fallback)

    def get_aggregator_prompt(self, version: str, fallback: str) -> str:
        data = self._load_version(version)
        return data.get("aggregator_system_prompt", fallback)

    def get_metadata(self, version: str) -> dict[str, Any]:
        data = self._load_version(version)
        return {
            key: value
            for key, value in data.items()
            if key not in ("system_prompt", "aggregator_system_prompt")
        }

    def list_versions(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(path.stem for path in self._dir.glob("*.yaml"))

    def clear_cache(self) -> None:
        self._cache.clear()


_default_registry: PromptRegistry | None = None


def get_registry() -> PromptRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = PromptRegistry()
    return _default_registry
