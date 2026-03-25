"""체크포인트 파일에서 분석 결과를 LLM 호출 없이 확인하는 뷰어.

사용법:
  python -m LLMEngine.entrypoints.checkpoint_viewer [--checkpoint CHECKPOINT_FILE] [--all]
  python -m LLMEngine.entrypoints.checkpoint_viewer                     # 미완료 체크포인트 자동 탐색
  python -m LLMEngine.entrypoints.checkpoint_viewer --all               # 모든 체크포인트 요약
  python -m LLMEngine.entrypoints.checkpoint_viewer --checkpoint checkpoints/260205_03_checkpoint.json
  python -m LLMEngine.entrypoints.checkpoint_viewer --export            # 미완료 체크포인트 → output JSON 내보내기
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from functools import reduce
from pathlib import Path


def load_checkpoint(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def summarize_checkpoint(cp_path: Path, *, verbose: bool = False) -> None:
    data = load_checkpoint(cp_path)
    lecture_id = cp_path.stem.replace("_checkpoint", "")

    total = len(data)
    success = [cid for cid, v in data.items() if v.get("status") == "SUCCESS"]
    failed = [cid for cid, v in data.items() if v.get("status") == "FAILED"]
    processing = [cid for cid, v in data.items() if v.get("status") == "PROCESSING"]

    print(f"\n{'='*70}")
    print(f"  {lecture_id}")
    print(f"  파일: {cp_path}")
    print(f"{'='*70}")
    print(f"  전체 청크: {total}  |  SUCCESS: {len(success)}  |  FAILED: {len(failed)}  |  PROCESSING: {len(processing)}")

    results = []
    for cid in sorted(data.keys(), key=lambda x: int(x)):
        entry = data[cid]
        status = entry.get("status", "UNKNOWN")
        if status == "SUCCESS" and "result" in entry:
            results.append(entry["result"])
        if verbose:
            marker = "O" if status == "SUCCESS" else ("X" if status == "FAILED" else "~")
            reason = ""
            if status == "FAILED" and "failure_reason" in entry:
                reason = f"  ({entry['failure_reason'][:60]}...)" if len(entry.get("failure_reason", "")) > 60 else f"  ({entry.get('failure_reason', '')})"
            print(f"    [{marker}] chunk {cid:>2}: {status}{reason}")

    if not results:
        print("  성공한 청크가 없습니다.")
        return

    print(f"\n  ── 성공 청크 점수 요약 ({len(results)}개) ──")

    item_scores: dict[str, list[int]] = defaultdict(list)
    for r in results:
        scores = r.get("scores", {})
        for cat_name, items in scores.items():
            if not isinstance(items, dict):
                continue
            for item_name, val in items.items():
                if val is not None:
                    item_scores[item_name].append(val)

    categories = {
        "강의 구조 (lecture_structure)": [
            "learning_objective_intro", "previous_lesson_linkage",
            "explanation_sequence", "key_point_emphasis", "closing_summary",
        ],
        "개념 명확성 (concept_clarity)": [
            "concept_definition", "analogy_example_usage", "prerequisite_check",
        ],
        "실습 연계 (practice_linkage)": [
            "example_appropriateness", "practice_transition", "error_handling",
        ],
        "상호작용 (interaction)": [
            "participation_induction", "question_response_sufficiency",
        ],
    }

    for cat_label, items in categories.items():
        print(f"\n  [{cat_label}]")
        for item in items:
            vals = item_scores.get(item, [])
            if not vals:
                print(f"    {item:.<40s} N/A")
            else:
                avg = sum(vals) / len(vals)
                mn, mx = min(vals), max(vals)
                print(f"    {item:.<40s} 평균 {avg:.1f}  (min={mn}, max={mx}, n={len(vals)})")

    rel_metrics = []
    for r in results:
        rel = r.get("reliability")
        if rel:
            rel_metrics.append(rel)

    if rel_metrics:
        n = len(rel_metrics)
        avg_pass = sum(m["evidence_pass_ratio"] for m in rel_metrics) / n
        avg_sim = sum(m["avg_evidence_similarity"] for m in rel_metrics) / n
        avg_con = sum(m["score_evidence_consistency"] for m in rel_metrics) / n
        avg_rel = sum(m["overall_reliability_score"] for m in rel_metrics) / n
        total_h = sum(m["hallucination_retries"] for m in rel_metrics)
        print(f"\n  ── 신뢰도 지표 ──")
        print(f"    evidence_pass_ratio ......... {avg_pass:.4f}")
        print(f"    avg_evidence_similarity ..... {avg_sim:.2f}")
        print(f"    score_evidence_consistency .. {avg_con:.4f}")
        print(f"    hallucination_retries ....... {total_h}")
        print(f"    overall_reliability_score ... {avg_rel:.4f}")

    evidence_count = sum(len(r.get("evidence", [])) for r in results)
    print(f"\n  총 evidence 수: {evidence_count}")

    if verbose and evidence_count > 0:
        print(f"\n  ── evidence 샘플 (항목별 첫 번째) ──")
        seen: set[str] = set()
        for r in results:
            for ev in r.get("evidence", []):
                item = ev.get("item", "?")
                if item not in seen:
                    seen.add(item)
                    quote = ev.get("quote", "")[:80]
                    reason = ev.get("reason", "")[:80]
                    print(f"    [{item}]")
                    print(f"      인용: {quote}...")
                    print(f"      근거: {reason}...")


def export_checkpoint_to_output(cp_path: Path, out_dir: Path) -> tuple[Path | None, Path | None]:
    """체크포인트 데이터에서 LLM 호출 없이 output JSON을 생성한다."""
    from LLMEngine.core.schemas import (
        AggregatedAnalysis, AggregatedResult, ChunkResult, ChunkStatus,
        Evidence, ReliabilityMetrics, RunMetadata, SummaryScores, TokenUsage,
    )

    data = load_checkpoint(cp_path)
    lecture_id = cp_path.stem.replace("_checkpoint", "")

    results: list[ChunkResult] = []
    for cid in sorted(data.keys(), key=lambda x: int(x)):
        entry = data[cid]
        if entry.get("status") == "SUCCESS" and "result" in entry:
            results.append(ChunkResult.model_validate(entry["result"]))

    if not results:
        print(f"  [{lecture_id}] 성공한 청크가 없어 내보내기 불가")
        return None, None

    scoring = [c for c in results if not c.is_fallback and c.status == ChunkStatus.SUCCESS]
    if not scoring:
        scoring = list(results)

    dumps = [c.scores.model_dump() for c in scoring]
    summary_dict: dict[str, dict[str, float | None]] = {}
    for category, items in dumps[0].items():
        summary_dict[category] = {}
        for item in items:
            values = [d[category][item] for d in dumps if d[category].get(item) is not None]
            summary_dict[category][item] = round(sum(values) / len(values), 1) if values else None
    summary_scores = SummaryScores.model_validate(summary_dict)

    all_strengths = [t for c in results for t in (c.strengths or []) if t and "기본값" not in t]
    all_issues = [t for c in results for t in (c.issues or []) if t and "기본값" not in t]
    unique_strengths = list(dict.fromkeys(all_strengths))[:10]
    unique_issues = list(dict.fromkeys(all_issues))[:10]

    seen_ev: dict[str, Evidence] = {}
    for c in scoring:
        for ev in (c.evidence or []):
            if ev.item not in seen_ev:
                seen_ev[ev.item] = ev
    overall_evidences = list(seen_ev.values())[:25]

    chunk_usage = reduce(
        lambda a, b: a + b,
        (c.token_usage for c in results if c.token_usage),
        TokenUsage(),
    )

    total_chunks = len(data)
    with_rel = [c for c in results if c.reliability is not None]
    if with_rel:
        n = len(with_rel)
        agg_rel = ReliabilityMetrics(
            evidence_pass_ratio=round(sum(r.reliability.evidence_pass_ratio for r in with_rel) / n, 4),
            hallucination_retries=sum(r.reliability.hallucination_retries for r in with_rel),
            avg_evidence_similarity=round(sum(r.reliability.avg_evidence_similarity for r in with_rel) / n, 2),
            score_evidence_consistency=round(sum(r.reliability.score_evidence_consistency for r in with_rel) / n, 4),
            overall_reliability_score=round(sum(r.reliability.overall_reliability_score for r in with_rel) / n, 4),
        )
    else:
        agg_rel = ReliabilityMetrics(overall_reliability_score=0.0)

    failed_count = sum(1 for v in data.values() if v.get("status") == "FAILED")

    run_metadata = RunMetadata(
        prompt_version="(checkpoint export)",
        model="(checkpoint export)",
        total_chunks=total_chunks,
        scored_chunks=len(scoring),
        successful_chunks=len(results),
        fallback_chunks=sum(1 for c in results if c.is_fallback),
        refused_chunks=0,
        failed_chunks=failed_count,
        evidence_count_total=sum(len(c.evidence) for c in results),
        token_usage=chunk_usage,
        reliability=agg_rel,
    )

    aggregated = AggregatedResult(
        llm_aggregated_analysis=AggregatedAnalysis(
            summary_scores=summary_scores,
            overall_strengths=unique_strengths,
            overall_issues=unique_issues,
            overall_evidences=overall_evidences,
        ),
        run_metadata=run_metadata,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = out_dir / f"{lecture_id}_chunks.json"
    summary_path = out_dir / f"{lecture_id}_summary.json"

    with chunks_path.open("w", encoding="utf-8") as f:
        json.dump([c.model_dump(mode="json") for c in results], f, ensure_ascii=False, indent=2)
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(aggregated.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

    print(f"  [{lecture_id}] 내보내기 완료: {len(results)}/{total_chunks} 성공 청크")
    print(f"    chunks → {chunks_path}")
    print(f"    summary → {summary_path}")
    return chunks_path, summary_path


def find_incomplete_checkpoints(cp_dir: Path, out_dir: Path) -> list[Path]:
    incomplete = []
    for cp_file in sorted(cp_dir.glob("*_checkpoint.json")):
        lecture_id = cp_file.stem.replace("_checkpoint", "")
        summary = out_dir / f"{lecture_id}_summary.json"
        if not summary.exists():
            incomplete.append(cp_file)
    return incomplete


def main() -> None:
    parser = argparse.ArgumentParser(description="체크포인트 결과 뷰어")
    parser.add_argument("--checkpoint", "-c", type=str, help="특정 체크포인트 파일 경로")
    parser.add_argument("--all", "-a", action="store_true", help="모든 체크포인트 요약")
    parser.add_argument("--verbose", "-v", action="store_true", help="상세 출력 (청크별 상태, evidence 샘플)")
    parser.add_argument("--export", "-e", action="store_true", help="미완료 체크포인트를 output JSON으로 내보내기 (LLM 호출 없음)")
    parser.add_argument("--checkpoint-dir", type=str, default="./checkpoints")
    parser.add_argument("--output-dir", type=str, default="./output")
    args = parser.parse_args()

    cp_dir = Path(args.checkpoint_dir)
    out_dir = Path(args.output_dir)

    if args.export:
        if not cp_dir.exists():
            print(f"체크포인트 디렉토리가 없습니다: {cp_dir}", file=sys.stderr)
            sys.exit(1)

        if args.checkpoint:
            targets = [Path(args.checkpoint)]
        else:
            targets = find_incomplete_checkpoints(cp_dir, out_dir)

        if not targets:
            print("내보낼 미완료 체크포인트가 없습니다.")
            return

        print(f"체크포인트 {len(targets)}개 → output 내보내기:")
        for cp_file in targets:
            export_checkpoint_to_output(cp_file, out_dir)
        print("\n완료. 강점/이슈 요약은 LLM 미사용으로 청크별 원본 그대로 수집되었습니다.")
        return

    if args.checkpoint:
        cp = Path(args.checkpoint)
        if not cp.exists():
            print(f"파일을 찾을 수 없습니다: {cp}", file=sys.stderr)
            sys.exit(1)
        summarize_checkpoint(cp, verbose=args.verbose)
        return

    if not cp_dir.exists():
        print(f"체크포인트 디렉토리가 없습니다: {cp_dir}", file=sys.stderr)
        sys.exit(1)

    if args.all:
        targets = sorted(cp_dir.glob("*_checkpoint.json"))
    else:
        targets = find_incomplete_checkpoints(cp_dir, out_dir)
        if not targets:
            print("미완료 체크포인트가 없습니다. 모든 강의가 정상 완료되었습니다.")
            return
        print(f"미완료 체크포인트 {len(targets)}개 발견:")

    for cp_file in targets:
        summarize_checkpoint(cp_file, verbose=args.verbose)

    print()


if __name__ == "__main__":
    main()
