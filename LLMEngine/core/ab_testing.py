"""멀티 모델 A/B 테스트 인프라.

동일 입력에 대해 여러 LLM 모델을 병렬로 실행하고
결과를 비교하는 유틸리티.

사용 예:
    runner = ABTestRunner([openai_adapter, gemini_adapter])
    results = runner.run_comparison(chunks)
    print(runner.compare_scores(results))
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from LLMEngine.core.ports import ILLMProvider
from LLMEngine.core.schemas import ChunkMetadata, ChunkResult, ChunkScores

logger = logging.getLogger(__name__)


@dataclass
class ModelResult:
    model_name: str
    chunk_results: list[ChunkResult]
    total_cost_usd: float = 0.0
    total_duration_s: float = 0.0


@dataclass
class ABComparison:
    """두 모델 간 비교 결과."""
    model_a: str
    model_b: str
    item_diffs: dict[str, float] = field(default_factory=dict)
    cost_ratio: float = 0.0
    agreement_ratio: float = 0.0


class ABTestRunner:
    """멀티 모델 A/B 테스트 러너."""

    def __init__(self, providers: list[ILLMProvider]) -> None:
        if len(providers) < 2:
            raise ValueError("A/B 테스트에는 최소 2개의 LLM provider가 필요합니다.")
        self.providers = providers

    def run_comparison(
        self, chunks: list[ChunkMetadata], *, use_async: bool = False,
    ) -> list[ModelResult]:
        """모든 provider로 동일 청크를 처리하고 결과를 수집한다."""
        results: list[ModelResult] = []
        for provider in self.providers:
            chunk_results: list[ChunkResult] = []
            for chunk in chunks:
                try:
                    result = provider.analyze_chunk(chunk)
                    chunk_results.append(result)
                except Exception as e:
                    logger.error("A/B test %s chunk=%d 실패: %s",
                                 provider.model_name, chunk.chunk_id, e)

            total_cost = sum(
                float(r.token_usage.estimated_cost_usd)
                for r in chunk_results if r.token_usage
            )
            results.append(ModelResult(
                model_name=provider.model_name,
                chunk_results=chunk_results,
                total_cost_usd=total_cost,
            ))
        return results

    @staticmethod
    def compare_scores(results: list[ModelResult]) -> list[ABComparison]:
        """모든 모델 쌍에 대해 점수 차이를 계산한다."""
        comparisons: list[ABComparison] = []
        for i in range(len(results)):
            for j in range(i + 1, len(results)):
                a, b = results[i], results[j]
                item_diffs = _compute_avg_score_diff(a.chunk_results, b.chunk_results)
                agreement = _compute_agreement_ratio(a.chunk_results, b.chunk_results)
                cost_ratio = (a.total_cost_usd / b.total_cost_usd) if b.total_cost_usd > 0 else 0.0
                comparisons.append(ABComparison(
                    model_a=a.model_name,
                    model_b=b.model_name,
                    item_diffs=item_diffs,
                    cost_ratio=round(cost_ratio, 3),
                    agreement_ratio=round(agreement, 4),
                ))
        return comparisons

    @staticmethod
    def save_comparison(
        results: list[ModelResult],
        comparisons: list[ABComparison],
        output_path: Path | str,
    ) -> None:
        """비교 결과를 JSON으로 저장한다."""
        output = {
            "models": [
                {
                    "model": r.model_name,
                    "chunks_processed": len(r.chunk_results),
                    "total_cost_usd": r.total_cost_usd,
                }
                for r in results
            ],
            "comparisons": [
                {
                    "model_a": c.model_a,
                    "model_b": c.model_b,
                    "item_diffs": c.item_diffs,
                    "cost_ratio": c.cost_ratio,
                    "agreement_ratio": c.agreement_ratio,
                }
                for c in comparisons
            ],
        }
        Path(output_path).write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _flatten_scores(scores: ChunkScores) -> dict[str, int | None]:
    flat: dict[str, int | None] = {}
    for cat in scores.model_dump().values():
        if isinstance(cat, dict):
            flat.update(cat)
    return flat


def _compute_avg_score_diff(
    a_results: list[ChunkResult],
    b_results: list[ChunkResult],
) -> dict[str, float]:
    """공통 chunk_id에 대해 항목별 평균 점수 차이를 계산한다."""
    a_map = {r.chunk_id: r for r in a_results}
    b_map = {r.chunk_id: r for r in b_results}
    common_ids = set(a_map.keys()) & set(b_map.keys())

    diffs: dict[str, list[float]] = {}
    for cid in common_ids:
        a_flat = _flatten_scores(a_map[cid].scores)
        b_flat = _flatten_scores(b_map[cid].scores)
        for item in a_flat:
            a_val, b_val = a_flat.get(item), b_flat.get(item)
            if a_val is not None and b_val is not None:
                diffs.setdefault(item, []).append(a_val - b_val)

    return {
        item: round(sum(vals) / len(vals), 2)
        for item, vals in diffs.items()
        if vals
    }


def _compute_agreement_ratio(
    a_results: list[ChunkResult],
    b_results: list[ChunkResult],
) -> float:
    """두 모델이 동일 점수를 부여한 비율."""
    a_map = {r.chunk_id: r for r in a_results}
    b_map = {r.chunk_id: r for r in b_results}
    common_ids = set(a_map.keys()) & set(b_map.keys())

    total = 0
    agree = 0
    for cid in common_ids:
        a_flat = _flatten_scores(a_map[cid].scores)
        b_flat = _flatten_scores(b_map[cid].scores)
        for item in a_flat:
            a_val, b_val = a_flat.get(item), b_flat.get(item)
            if a_val is not None and b_val is not None:
                total += 1
                if a_val == b_val:
                    agree += 1
    return agree / total if total > 0 else 0.0
