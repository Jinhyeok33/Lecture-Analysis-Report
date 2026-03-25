"""청크별 LLM 분석 결과 통합 모듈."""

from __future__ import annotations

import logging
from collections import defaultdict
from functools import reduce
from typing import List

from LLMEngine.core.schemas import (
    AggregatedAnalysis, AggregatedResult, ChunkResult, ChunkStatus, Evidence,
    ReliabilityMetrics, RunMetadata, SummaryScores, TokenUsage,
)
from LLMEngine.core.ports import ILLMProvider
from LLMEngine.application.prompts import PROMPT_VERSION

logger = logging.getLogger(__name__)


class ResultAggregator:
    def __init__(self, llm_provider: ILLMProvider) -> None:
        self.llm = llm_provider

    def aggregate(self, chunk_results: list[ChunkResult]) -> AggregatedResult:
        if not chunk_results:
            raise ValueError("청크 결과가 최소 1개 필요합니다.")

        scoring = [c for c in chunk_results if not c.is_fallback and c.status == ChunkStatus.SUCCESS]
        if not scoring:
            logger.warning("stage=aggregate 모든 청크가 fallback/실패 — 전체 청크로 집계")
            scoring = list(chunk_results)

        summary_scores = self._calculate_summary_scores(scoring)
        scores_context = self._build_scores_context(summary_scores)
        score_trends = self._extract_score_trends(scoring)

        raw_strengths = [
            t for c in chunk_results for t in (c.strengths or [])
            if t and "특이사항" not in t and "기본값" not in t
        ]
        raw_issues = [
            t for c in chunk_results for t in (c.issues or [])
            if t and "특이사항" not in t and "기본값" not in t
        ]

        strength_items, issue_items = self._partition_items_by_score(summary_scores)
        enriched_scores_ctx = (
            scores_context
            + f"\n\n[강점 대상 항목 (>3.0)]: {', '.join(strength_items) if strength_items else '없음'}"
            + f"\n[이슈 대상 항목 (<3.0)]: {', '.join(issue_items) if issue_items else '없음'}"
        )

        overall_strengths, str_usage = self.llm.aggregate_results(
            raw_strengths, "강점", enriched_scores_ctx, score_trends,
        )
        overall_issues, iss_usage = self.llm.aggregate_results(
            raw_issues, "이슈", enriched_scores_ctx, score_trends,
        )
        aggregation_usage = str_usage + iss_usage

        overall_evidences = self._select_representative_evidences(scoring, summary_scores)

        chunk_usage = reduce(
            lambda a, b: a + b,
            (c.token_usage for c in chunk_results if c.token_usage),
            TokenUsage(),
        )

        agg_reliability = self._aggregate_reliability(chunk_results)

        run_metadata = RunMetadata(
            prompt_version=PROMPT_VERSION,
            model=self.llm.model_name,
            total_chunks=len(chunk_results),
            scored_chunks=len(scoring),
            successful_chunks=sum(1 for c in chunk_results if c.status == ChunkStatus.SUCCESS),
            fallback_chunks=sum(1 for c in chunk_results if c.is_fallback),
            refused_chunks=sum(1 for c in chunk_results if c.status == ChunkStatus.REFUSED),
            failed_chunks=sum(
                1 for c in chunk_results
                if c.status in (ChunkStatus.FAILED, ChunkStatus.TIMED_OUT)
            ),
            evidence_count_total=sum(len(c.evidence) for c in chunk_results),
            token_usage=chunk_usage + aggregation_usage,
            reliability=agg_reliability,
        )

        if run_metadata.fallback_chunks > 0:
            logger.warning(
                "stage=aggregate fallback=%d total=%d scored=%d — fallback 제외 집계",
                run_metadata.fallback_chunks, run_metadata.total_chunks, run_metadata.scored_chunks,
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

    # ── 내부 집계 ────────────────────────────────────────────────────

    def _build_scores_context(self, summary_scores: SummaryScores) -> str:
        lines: list[str] = []
        for category, items in summary_scores.model_dump().items():
            lines.append(f"[{category}]")
            for name, score in items.items():
                if score is not None:
                    lines.append(f" - {name}: {score}점")
        return "\n".join(lines)

    def _calculate_summary_scores(self, chunks: List[ChunkResult]) -> SummaryScores:
        dumps = [c.scores.model_dump() for c in chunks]
        summary: dict[str, dict[str, float | None]] = {}
        for category, items in dumps[0].items():
            summary[category] = {}
            for item in items:
                values = [d[category][item] for d in dumps if d[category].get(item) is not None]
                summary[category][item] = round(sum(values) / len(values), 1) if values else None
        return SummaryScores.model_validate(summary)

    def _extract_score_trends(self, chunks: List[ChunkResult]) -> str:
        item_scores: dict[str, list[int]] = defaultdict(list)
        for c in chunks:
            for cat, items in c.scores.model_dump().items():
                if not isinstance(items, dict):
                    continue
                for name, val in items.items():
                    if val is not None:
                        item_scores[name].append(val)

        trends = [
            f"- [{name}]: 최저 {min(scores)}점 ~ 최고 {max(scores)}점 편차"
            for name, scores in item_scores.items()
            if scores and max(scores) - min(scores) >= 2
        ]
        return "\n".join(trends) if trends else "특이한 점수 편차 없음."

    def _select_representative_evidences(
        self, chunks: List[ChunkResult], summary_scores: SummaryScores,
    ) -> List[Evidence]:
        item_scores = [
            (item, float(val))
            for cat, items in summary_scores.model_dump().items()
            if isinstance(items, dict)
            for item, val in items.items()
            if val is not None
        ]
        if not item_scores:
            return self._first_per_item(chunks)[:25]

        item_scores.sort(key=lambda x: x[1])
        bottom = [i for i, _ in item_scores[:5]]
        top = [i for i, _ in item_scores[-5:]]
        target = list(dict.fromkeys(bottom + top))

        grouped: dict[str, list[Evidence]] = {}
        for c in chunks:
            for ev in (c.evidence or []):
                grouped.setdefault(ev.item, []).append(ev)

        result = [grouped[item][0] for item in target if item in grouped]

        if len(result) < 8:
            existing = {e.item for e in result}
            for ev in self._first_per_item(chunks):
                if ev.item not in existing:
                    result.append(ev)
                if len(result) >= 8:
                    break

        return result[:25]

    @staticmethod
    def _partition_items_by_score(summary_scores: SummaryScores) -> tuple[list[str], list[str]]:
        """3.0 초과 항목(강점 후보)과 3.0 미만 항목(이슈 후보)으로 분리."""
        strength_items: list[str] = []
        issue_items: list[str] = []
        for cat, items in summary_scores.model_dump().items():
            if not isinstance(items, dict):
                continue
            for item, val in items.items():
                if val is None:
                    continue
                if val > 3.0:
                    strength_items.append(item)
                elif val < 3.0:
                    issue_items.append(item)
        return strength_items, issue_items

    @staticmethod
    def _aggregate_reliability(chunks: List[ChunkResult]) -> ReliabilityMetrics:
        with_rel = [c for c in chunks if c.reliability is not None]
        if not with_rel:
            fallback_ratio = sum(1 for c in chunks if c.is_fallback) / max(len(chunks), 1)
            return ReliabilityMetrics(
                overall_reliability_score=round(1.0 - fallback_ratio, 4),
            )
        n = len(with_rel)
        avg_pass = sum(r.reliability.evidence_pass_ratio for r in with_rel) / n
        total_h = sum(r.reliability.hallucination_retries for r in with_rel)
        avg_sim = sum(r.reliability.avg_evidence_similarity for r in with_rel) / n
        avg_con = sum(r.reliability.score_evidence_consistency for r in with_rel) / n
        avg_overall = sum(r.reliability.overall_reliability_score for r in with_rel) / n

        fallback_penalty = sum(1 for c in chunks if c.is_fallback) / max(len(chunks), 1)

        return ReliabilityMetrics(
            evidence_pass_ratio=round(avg_pass, 4),
            hallucination_retries=total_h,
            avg_evidence_similarity=round(avg_sim, 2),
            score_evidence_consistency=round(avg_con, 4),
            overall_reliability_score=round(max(avg_overall - fallback_penalty * 0.15, 0.0), 4),
        )

    @staticmethod
    def _first_per_item(chunks: List[ChunkResult]) -> List[Evidence]:
        seen: dict[str, Evidence] = {}
        for c in chunks:
            for ev in (c.evidence or []):
                if ev.item not in seen:
                    seen[ev.item] = ev
        return list(seen.values())
