"""청크별 LLM 분석 결과 통합 모듈."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Iterable, List

from core.schemas import AggregatedResult, ChunkResult, Evidence, SummaryScores
from core.ports import ILLMProvider

logger = logging.getLogger(__name__)

class ResultAggregator:
    def __init__(self, llm_provider: ILLMProvider) -> None:
        self.llm = llm_provider

    def aggregate(self, chunk_results: Iterable[ChunkResult]) -> AggregatedResult:
        validated = [ChunkResult.model_validate(item) for item in chunk_results]
        if not validated:
            raise ValueError("청크 결과가 최소 1개 필요합니다.")

        summary_scores = self._calculate_summary_scores(validated)
        score_trends = self._extract_score_trends(validated)

        # 에이전틱 워크플로우: 평균 점수를 LLM 주입용 텍스트 컨텍스트로 변환
        scores_context = self._build_scores_context(summary_scores)

        # Fact Collector 노이즈 필터링 ("특이사항 없음" 등 불필요한 텍스트 제거)
        raw_strengths = [t for chunk in validated for t in (chunk.strengths or []) if t and "특이사항" not in t]
        raw_issues = [t for chunk in validated for t in (chunk.issues or []) if t and "특이사항" not in t]

        overall_strengths = self.llm.aggregate_results(raw_strengths, "강점", scores_context, score_trends)
        overall_issues = self.llm.aggregate_results(raw_issues, "이슈", scores_context, score_trends)

        overall_evidences = self._aggregate_evidences_optimized(validated, summary_scores)

        return AggregatedResult.model_validate(
            {
                "llm_aggregated_analysis": {
                    "summary_scores": summary_scores.model_dump(),
                    "overall_strengths": overall_strengths,
                    "overall_issues": overall_issues,
                    "overall_evidences": [item.model_dump() for item in overall_evidences],
                }
            }
        )

    def _build_scores_context(self, summary_scores: SummaryScores) -> str:
        """평균 점수를 LLM이 읽기 쉬운 텍스트 형식으로 직렬화합니다."""
        context_lines = []
        dump = summary_scores.model_dump()
        for category, items in dump.items():
            context_lines.append(f"[{category}]")
            for item_name, score in items.items():
                if score is not None:
                    context_lines.append(f" - {item_name}: {score}점")
        return "\n".join(context_lines)

    def _calculate_summary_scores(self, chunk_results: List[ChunkResult]) -> SummaryScores:
        first = chunk_results[0].scores.model_dump()
        summary: dict[str, dict[str, float | None]] = {}

        for category, item_scores in first.items():
            summary[category] = {}
            for item in item_scores:
                values = [
                    chunk.scores.model_dump()[category][item]
                    for chunk in chunk_results
                    if chunk.scores.model_dump()[category].get(item) is not None
                ]
                if values:
                    summary[category][item] = round(sum(values) / len(values), 1)
                else:
                    summary[category][item] = None

        return SummaryScores.model_validate(summary)

    def _extract_score_trends(self, chunk_results: List[ChunkResult]) -> str:
        item_scores_map: dict[str, list[int]] = defaultdict(list)
        for chunk in chunk_results:
            dump = chunk.scores.model_dump()
            for cat, items in dump.items():
                if not isinstance(items, dict):
                    continue
                for item_name, val in items.items():
                    if val is not None:
                        item_scores_map[item_name].append(val)

        trends: List[str] = []
        for item_name, scores in item_scores_map.items():
            if not scores:
                continue
            min_score, max_score = min(scores), max(scores)
            if max_score - min_score >= 2:
                trends.append(f"- [{item_name}]: 최저 {min_score}점 ~ 최고 {max_score}점 편차 발생.")
        return "\n".join(trends) if trends else "특이한 점수 편차 없음."

    def _aggregate_evidences(self, chunk_results: List[ChunkResult]) -> List[Evidence]:
        grouped: dict[str, list[Evidence]] = {}
        for chunk in chunk_results:
            for evidence in (chunk.evidence or []):
                grouped.setdefault(evidence.item, []).append(evidence)

        representatives: List[Evidence] = []
        for item in sorted(grouped):
            representatives.append(grouped[item][0])
        return representatives

    def _aggregate_evidences_optimized(
        self,
        chunk_results: List[ChunkResult],
        summary_scores: SummaryScores,
    ) -> List[Evidence]:
        item_scores: list[tuple[str, float]] = []
        for category, item_scores_dict in summary_scores.model_dump().items():
            if not isinstance(item_scores_dict, dict):
                continue
            for item, val in item_scores_dict.items():
                if val is not None:
                    item_scores.append((item, float(val)))
                    
        if not item_scores:
            return self._aggregate_evidences(chunk_results)[:25]

        item_scores.sort(key=lambda x: x[1])
        bottom_5_items = [item for item, _ in item_scores[:5]]
        top_5_items = [item for item, _ in item_scores[-5:]]
        target_items = list(dict.fromkeys(bottom_5_items + top_5_items))

        grouped: dict[str, list[Evidence]] = {}
        for chunk in chunk_results:
            for evidence in (chunk.evidence or []):
                grouped.setdefault(evidence.item, []).append(evidence)

        result: List[Evidence] = []
        for item in target_items:
            if item in grouped:
                result.append(grouped[item][0])

        if len(result) < 8:
            existing_items = {ev.item for ev in result}
            all_evidences = self._aggregate_evidences(chunk_results)
            for ev in all_evidences:
                if ev.item not in existing_items:
                    result.append(ev)
                if len(result) >= 8:
                    break

        return result[:25]