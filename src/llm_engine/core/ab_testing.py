"""Utilities for comparing multiple LLM providers on the same chunks."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.llm_engine.core.ports import ILLMProvider
from src.llm_engine.core.schemas import ChunkMetadata, ChunkResult, ChunkScores

logger = logging.getLogger(__name__)


@dataclass
class ModelResult:
    model_name: str
    chunk_results: list[ChunkResult]
    total_cost_usd: float = 0.0
    total_duration_s: float = 0.0


@dataclass
class ABComparison:
    model_a: str
    model_b: str
    item_diffs: dict[str, float] = field(default_factory=dict)
    cost_ratio: float = 0.0
    agreement_ratio: float = 0.0


class ABTestRunner:
    def __init__(self, providers: list[ILLMProvider]) -> None:
        if len(providers) < 2:
            raise ValueError("A/B testing requires at least two providers")
        self.providers = providers

    def run_comparison(
        self,
        chunks: list[ChunkMetadata],
        *,
        use_async: bool = False,
    ) -> list[ModelResult]:
        del use_async  # reserved for future async comparison support
        results: list[ModelResult] = []
        for provider in self.providers:
            chunk_results: list[ChunkResult] = []
            for chunk in chunks:
                try:
                    chunk_results.append(provider.analyze_chunk(chunk))
                except Exception as exc:
                    logger.error("A/B test %s chunk=%d failed: %s", provider.model_name, chunk.chunk_id, exc)

            total_cost = sum(
                float(result.token_usage.estimated_cost_usd)
                for result in chunk_results
                if result.token_usage
            )
            results.append(
                ModelResult(
                    model_name=provider.model_name,
                    chunk_results=chunk_results,
                    total_cost_usd=total_cost,
                )
            )
        return results

    @staticmethod
    def compare_scores(results: list[ModelResult]) -> list[ABComparison]:
        comparisons: list[ABComparison] = []
        for index in range(len(results)):
            for other_index in range(index + 1, len(results)):
                left, right = results[index], results[other_index]
                comparisons.append(
                    ABComparison(
                        model_a=left.model_name,
                        model_b=right.model_name,
                        item_diffs=_compute_avg_score_diff(left.chunk_results, right.chunk_results),
                        cost_ratio=round(
                            (left.total_cost_usd / right.total_cost_usd) if right.total_cost_usd > 0 else 0.0,
                            3,
                        ),
                        agreement_ratio=round(
                            _compute_agreement_ratio(left.chunk_results, right.chunk_results),
                            4,
                        ),
                    )
                )
        return comparisons

    @staticmethod
    def save_comparison(
        results: list[ModelResult],
        comparisons: list[ABComparison],
        output_path: Path | str,
    ) -> None:
        payload = {
            "models": [
                {
                    "model": result.model_name,
                    "chunks_processed": len(result.chunk_results),
                    "total_cost_usd": result.total_cost_usd,
                }
                for result in results
            ],
            "comparisons": [
                {
                    "model_a": comparison.model_a,
                    "model_b": comparison.model_b,
                    "item_diffs": comparison.item_diffs,
                    "cost_ratio": comparison.cost_ratio,
                    "agreement_ratio": comparison.agreement_ratio,
                }
                for comparison in comparisons
            ],
        }
        Path(output_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _flatten_scores(scores: ChunkScores) -> dict[str, int | None]:
    flat: dict[str, int | None] = {}
    for category in scores.model_dump().values():
        if isinstance(category, dict):
            flat.update(category)
    return flat


def _compute_avg_score_diff(
    left_results: list[ChunkResult],
    right_results: list[ChunkResult],
) -> dict[str, float]:
    left_map = {result.chunk_id: result for result in left_results}
    right_map = {result.chunk_id: result for result in right_results}
    common_ids = set(left_map) & set(right_map)

    diffs: dict[str, list[float]] = {}
    for chunk_id in common_ids:
        left_scores = _flatten_scores(left_map[chunk_id].scores)
        right_scores = _flatten_scores(right_map[chunk_id].scores)
        for item in left_scores:
            left_value, right_value = left_scores.get(item), right_scores.get(item)
            if left_value is not None and right_value is not None:
                diffs.setdefault(item, []).append(left_value - right_value)

    return {
        item: round(sum(values) / len(values), 2)
        for item, values in diffs.items()
        if values
    }


def _compute_agreement_ratio(
    left_results: list[ChunkResult],
    right_results: list[ChunkResult],
) -> float:
    left_map = {result.chunk_id: result for result in left_results}
    right_map = {result.chunk_id: result for result in right_results}
    common_ids = set(left_map) & set(right_map)

    total = 0
    agreed = 0
    for chunk_id in common_ids:
        left_scores = _flatten_scores(left_map[chunk_id].scores)
        right_scores = _flatten_scores(right_map[chunk_id].scores)
        for item in left_scores:
            left_value, right_value = left_scores.get(item), right_scores.get(item)
            if left_value is not None and right_value is not None:
                total += 1
                if left_value == right_value:
                    agreed += 1
    return agreed / total if total > 0 else 0.0
