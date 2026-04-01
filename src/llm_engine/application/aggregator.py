"""Aggregate chunk-level LLM analysis into a lecture-level result."""

from __future__ import annotations

import logging
from collections import defaultdict
from functools import reduce
from typing import Iterable, List

from src.llm_engine.application.prompts import PROMPT_VERSION
from src.llm_engine.core.ports import ILLMProvider
from src.llm_engine.core.schemas import (
    AggregatedAnalysis,
    AggregatedResult,
    ChunkResult,
    ChunkStatus,
    Evidence,
    ReliabilityMetrics,
    RunMetadata,
    SummaryScores,
    TokenUsage,
)

logger = logging.getLogger(__name__)


def _flatten_summary(scores: SummaryScores) -> dict[str, float | None]:
    flat: dict[str, float | None] = {}
    for items in scores.model_dump().values():
        if isinstance(items, dict):
            flat.update(items)
    return flat


class ResultAggregator:
    def __init__(self, llm_provider: ILLMProvider) -> None:
        self.llm = llm_provider

    def aggregate(self, chunk_results: Iterable[ChunkResult]) -> AggregatedResult:
        validated = [ChunkResult.model_validate(item) for item in chunk_results]
        if not validated:
            raise ValueError("At least one chunk result is required")

        scoring = [
            chunk
            for chunk in validated
            if not chunk.is_fallback and chunk.status == ChunkStatus.SUCCESS
        ]
        if not scoring:
            logger.warning("aggregate: all chunks are fallback/failed; using all chunks")
            scoring = list(validated)

        summary_scores = self._calculate_summary_scores(scoring)
        scores_context = self._build_scores_context(summary_scores)
        score_trends = self._extract_score_trends(scoring)

        raw_strengths = [
            text
            for chunk in validated
            for text in (chunk.strengths or [])
            if text and "특이사항" not in text and "기본값" not in text
        ]
        raw_issues = [
            text
            for chunk in validated
            for text in (chunk.issues or [])
            if text and "특이사항" not in text and "기본값" not in text
        ]

        strength_items, issue_items = self._partition_items_by_score(summary_scores)
        enriched_context = (
            scores_context
            + f"\n\n[강점 대상 항목 (>3.0)]: {', '.join(strength_items) if strength_items else '없음'}"
            + f"\n[이슈 대상 항목 (<3.0)]: {', '.join(issue_items) if issue_items else '없음'}"
        )

        overall_strengths, strength_usage = self.llm.aggregate_results(
            raw_strengths,
            "강점",
            enriched_context,
            score_trends,
        )
        overall_issues, issue_usage = self.llm.aggregate_results(
            raw_issues,
            "이슈",
            enriched_context,
            score_trends,
        )
        aggregation_usage = strength_usage + issue_usage

        overall_evidences = self._select_representative_evidences(scoring, summary_scores)

        chunk_usage = reduce(
            lambda acc, usage: acc + usage,
            (chunk.token_usage for chunk in validated if chunk.token_usage),
            TokenUsage(),
        )
        reliability = self._aggregate_reliability(validated)

        run_metadata = RunMetadata(
            prompt_version=PROMPT_VERSION,
            model=self.llm.model_name,
            total_chunks=len(validated),
            scored_chunks=len(scoring),
            successful_chunks=sum(1 for chunk in validated if chunk.status == ChunkStatus.SUCCESS),
            fallback_chunks=sum(1 for chunk in validated if chunk.is_fallback),
            refused_chunks=sum(1 for chunk in validated if chunk.status == ChunkStatus.REFUSED),
            failed_chunks=sum(
                1
                for chunk in validated
                if chunk.status in (ChunkStatus.FAILED, ChunkStatus.TIMED_OUT, ChunkStatus.CANCELLED)
            ),
            evidence_count_total=sum(len(chunk.evidence) for chunk in validated),
            token_usage=chunk_usage + aggregation_usage,
            reliability=reliability,
        )

        return AggregatedResult(
            llm_aggregated_analysis=AggregatedAnalysis(
                summary_scores=summary_scores,
                overall_strengths=overall_strengths,
                overall_issues=overall_issues,
                overall_evidences=overall_evidences,
            ),
            run_metadata=run_metadata,
        )

    def _build_scores_context(self, summary_scores: SummaryScores) -> str:
        lines: list[str] = []
        for category, items in summary_scores.model_dump().items():
            lines.append(f"[{category}]")
            for item_name, score in items.items():
                if score is not None:
                    lines.append(f" - {item_name}: {score}점")
        return "\n".join(lines)

    def _calculate_summary_scores(self, chunks: List[ChunkResult]) -> SummaryScores:
        dumps = [chunk.scores.model_dump() for chunk in chunks]
        summary: dict[str, dict[str, float | None]] = {}

        for category, items in dumps[0].items():
            summary[category] = {}
            for item in items:
                values = [dump[category][item] for dump in dumps if dump[category].get(item) is not None]
                summary[category][item] = round(sum(values) / len(values), 1) if values else None

        return SummaryScores.model_validate(summary)

    def _extract_score_trends(self, chunks: List[ChunkResult]) -> str:
        item_scores: dict[str, list[int]] = defaultdict(list)
        for chunk in chunks:
            for category, items in chunk.scores.model_dump().items():
                if not isinstance(items, dict):
                    continue
                for item_name, value in items.items():
                    if value is not None:
                        item_scores[item_name].append(value)

        trends = [
            f"- [{item_name}]: 최저 {min(scores)}점 ~ 최고 {max(scores)}점 편차"
            for item_name, scores in item_scores.items()
            if scores and max(scores) - min(scores) >= 2
        ]
        return "\n".join(trends) if trends else "특이한 점수 편차 없음."

    def _select_representative_evidences(
        self,
        chunks: List[ChunkResult],
        summary_scores: SummaryScores,
    ) -> List[Evidence]:
        flat = _flatten_summary(summary_scores)
        item_scores = [(item, value) for item, value in flat.items() if value is not None]
        if not item_scores:
            return self._first_per_item(chunks)[:25]

        item_scores.sort(key=lambda pair: pair[1])
        bottom = [item for item, _ in item_scores[:5]]
        top = [item for item, _ in item_scores[-5:]]
        target_items = list(dict.fromkeys(bottom + top))

        grouped: dict[str, list[Evidence]] = {}
        for chunk in chunks:
            for evidence in chunk.evidence or []:
                grouped.setdefault(evidence.item, []).append(evidence)

        results = [grouped[item][0] for item in target_items if item in grouped]

        if len(results) < 8:
            existing_items = {evidence.item for evidence in results}
            for evidence in self._first_per_item(chunks):
                if evidence.item not in existing_items:
                    results.append(evidence)
                    existing_items.add(evidence.item)
                if len(results) >= 8:
                    break

        return results[:25]

    @staticmethod
    def _partition_items_by_score(summary_scores: SummaryScores) -> tuple[list[str], list[str]]:
        flat = _flatten_summary(summary_scores)
        strengths = [item for item, value in flat.items() if value is not None and value > 3.0]
        issues = [item for item, value in flat.items() if value is not None and value < 3.0]
        return strengths, issues

    @staticmethod
    def _aggregate_reliability(chunks: List[ChunkResult]) -> ReliabilityMetrics:
        chunks_with_reliability = [chunk for chunk in chunks if chunk.reliability is not None]
        if not chunks_with_reliability:
            fallback_ratio = sum(1 for chunk in chunks if chunk.is_fallback) / max(len(chunks), 1)
            return ReliabilityMetrics(
                overall_reliability_score=round(1.0 - fallback_ratio, 4),
            )

        count = len(chunks_with_reliability)
        avg_pass_ratio = sum(chunk.reliability.evidence_pass_ratio for chunk in chunks_with_reliability) / count
        total_hallucination_retries = sum(
            chunk.reliability.hallucination_retries for chunk in chunks_with_reliability
        )
        avg_similarity = sum(
            chunk.reliability.avg_evidence_similarity for chunk in chunks_with_reliability
        ) / count
        avg_consistency = sum(
            chunk.reliability.score_evidence_consistency for chunk in chunks_with_reliability
        ) / count
        avg_overall = sum(
            chunk.reliability.overall_reliability_score for chunk in chunks_with_reliability
        ) / count

        fallback_penalty = sum(1 for chunk in chunks if chunk.is_fallback) / max(len(chunks), 1)

        return ReliabilityMetrics(
            evidence_pass_ratio=round(avg_pass_ratio, 4),
            hallucination_retries=total_hallucination_retries,
            avg_evidence_similarity=round(avg_similarity, 2),
            score_evidence_consistency=round(avg_consistency, 4),
            overall_reliability_score=round(max(avg_overall - fallback_penalty * 0.15, 0.0), 4),
        )

    @staticmethod
    def _first_per_item(chunks: List[ChunkResult]) -> List[Evidence]:
        seen: dict[str, Evidence] = {}
        for chunk in chunks:
            for evidence in chunk.evidence or []:
                if evidence.item not in seen:
                    seen[evidence.item] = evidence
        return list(seen.values())
