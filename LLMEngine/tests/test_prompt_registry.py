"""prompt_registry.py 단위 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest

from LLMEngine.core.prompt_registry import PromptRegistry


class TestPromptRegistry:
    def test_fallback_when_no_yaml(self, tmp_path):
        registry = PromptRegistry(prompt_dir=tmp_path)
        result = registry.get_system_prompt("v4.3", "기본 프롬프트")
        assert result == "기본 프롬프트"

    def test_fallback_aggregator(self, tmp_path):
        registry = PromptRegistry(prompt_dir=tmp_path)
        result = registry.get_aggregator_prompt("v4.3", "집계 프롬프트")
        assert result == "집계 프롬프트"

    def test_list_versions_empty(self, tmp_path):
        registry = PromptRegistry(prompt_dir=tmp_path)
        assert registry.list_versions() == []

    def test_list_versions_nonexistent_dir(self):
        registry = PromptRegistry(prompt_dir="/nonexistent/path")
        assert registry.list_versions() == []

    def test_cache_clear(self, tmp_path):
        registry = PromptRegistry(prompt_dir=tmp_path)
        registry.get_system_prompt("v1", "fallback")
        assert "v1" in registry._cache
        registry.clear_cache()
        assert len(registry._cache) == 0

    def test_yaml_loading(self, tmp_path):
        """pyyaml이 설치되어 있으면 YAML 로딩 확인."""
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml 미설치")

        yaml_content = {
            "system_prompt": "YAML 시스템 프롬프트",
            "aggregator_system_prompt": "YAML 집계 프롬프트",
            "version": "v_test",
            "author": "테스트",
        }
        yaml_path = tmp_path / "v_test.yaml"
        yaml_path.write_text(
            yaml.dump(yaml_content, allow_unicode=True),
            encoding="utf-8",
        )

        registry = PromptRegistry(prompt_dir=tmp_path)
        assert registry.get_system_prompt("v_test", "fallback") == "YAML 시스템 프롬프트"
        assert registry.get_aggregator_prompt("v_test", "fallback") == "YAML 집계 프롬프트"
        assert registry.get_metadata("v_test")["author"] == "테스트"
        assert "v_test" in registry.list_versions()

    def test_corrupted_yaml_returns_fallback(self, tmp_path):
        """잘못된 YAML 파일은 fallback으로 처리."""
        (tmp_path / "bad.yaml").write_text("{{invalid yaml:", encoding="utf-8")
        registry = PromptRegistry(prompt_dir=tmp_path)
        result = registry.get_system_prompt("bad", "안전한 프롬프트")
        assert result == "안전한 프롬프트"
