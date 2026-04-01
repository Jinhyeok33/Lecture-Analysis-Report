"""Inspect or export checkpointed chunk results without re-running the LLM."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from functools import reduce
from pathlib import Path

from src.common.naming import llm_chunks_json_path, llm_json_path
from src.llm_engine.core.ports import IRepository


def _make_repository(repo_type: str, checkpoint_dir: str = "./checkpoints") -> IRepository:
    if repo_type == "sqlite":
        from src.llm_engine.infrastructure.persistence.sqlite_repo import SQLiteRepository

        return SQLiteRepository(db_path=str(Path(checkpoint_dir) / "checkpoints.db"))

    from src.llm_engine.infrastructure.persistence.json_repo import LocalJsonRepository

    return LocalJsonRepository(base_dir=checkpoint_dir)


def load_checkpoint(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def summarize_checkpoint(checkpoint_path: Path, *, verbose: bool = False) -> None:
    data = load_checkpoint(checkpoint_path)
    lecture_id = checkpoint_path.stem.replace("_checkpoint", "")

    total = len(data)
    success = [chunk_id for chunk_id, value in data.items() if value.get("status") == "SUCCESS"]
    failed = [chunk_id for chunk_id, value in data.items() if value.get("status") == "FAILED"]
    processing = [chunk_id for chunk_id, value in data.items() if value.get("status") == "PROCESSING"]

    print(f"\n{'=' * 70}")
    print(f"  {lecture_id}")
    print(f"  file: {checkpoint_path}")
    print(f"{'=' * 70}")
    print(
        "  total chunks: %d  |  success: %d  |  failed: %d  |  processing: %d"
        % (total, len(success), len(failed), len(processing))
    )

    results = []
    for chunk_id in sorted(data.keys(), key=lambda value: int(value)):
        entry = data[chunk_id]
        status = entry.get("status", "UNKNOWN")
        if status == "SUCCESS" and "result" in entry:
            results.append(entry["result"])
        if verbose:
            marker = "O" if status == "SUCCESS" else ("X" if status == "FAILED" else "~")
            reason = ""
            if status == "FAILED" and "failure_reason" in entry:
                failure = entry.get("failure_reason", "")
                reason = f"  ({failure[:60]}...)" if len(failure) > 60 else f"  ({failure})"
            print(f"    [{marker}] chunk {int(chunk_id):>2}: {status}{reason}")

    if not results:
        print("  no successful chunks")
        return

    print(f"\n  -- successful chunk score summary ({len(results)}) --")

    item_scores: dict[str, list[int]] = defaultdict(list)
    for result in results:
        scores = result.get("scores", {})
        for _, items in scores.items():
            if not isinstance(items, dict):
                continue
            for item_name, value in items.items():
                if value is not None:
                    item_scores[item_name].append(value)

    categories = {
        "Structure": [
            "learning_objective_intro",
            "previous_lesson_linkage",
            "explanation_sequence",
            "key_point_emphasis",
            "closing_summary",
        ],
        "Concept clarity": [
            "concept_definition",
            "analogy_example_usage",
            "prerequisite_check",
        ],
        "Practice linkage": [
            "example_appropriateness",
            "practice_transition",
            "error_handling",
        ],
        "Interaction": [
            "participation_induction",
            "question_response_sufficiency",
        ],
    }

    for label, items in categories.items():
        print(f"\n  [{label}]")
        for item in items:
            values = item_scores.get(item, [])
            if not values:
                print(f"    {item:.<40s} N/A")
            else:
                avg = sum(values) / len(values)
                print(f"    {item:.<40s} avg {avg:.1f}  (min={min(values)}, max={max(values)}, n={len(values)})")

    reliabilities = [result.get("reliability") for result in results if result.get("reliability")]
    if reliabilities:
        count = len(reliabilities)
        print("\n  -- reliability --")
        print(
            "    evidence_pass_ratio ......... %.4f"
            % (sum(item["evidence_pass_ratio"] for item in reliabilities) / count)
        )
        print(
            "    avg_evidence_similarity ..... %.2f"
            % (sum(item["avg_evidence_similarity"] for item in reliabilities) / count)
        )
        print(
            "    score_evidence_consistency .. %.4f"
            % (sum(item["score_evidence_consistency"] for item in reliabilities) / count)
        )
        print(
            "    hallucination_retries ....... %d"
            % sum(item["hallucination_retries"] for item in reliabilities)
        )
        print(
            "    overall_reliability_score ... %.4f"
            % (sum(item["overall_reliability_score"] for item in reliabilities) / count)
        )

    evidence_count = sum(len(result.get("evidence", [])) for result in results)
    print(f"\n  total evidence count: {evidence_count}")


def export_checkpoint_to_output(checkpoint_path: Path, output_dir: Path) -> tuple[Path | None, Path | None]:
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

    data = load_checkpoint(checkpoint_path)
    lecture_id = checkpoint_path.stem.replace("_checkpoint", "")

    results: list[ChunkResult] = []
    for chunk_id in sorted(data.keys(), key=lambda value: int(value)):
        entry = data[chunk_id]
        if entry.get("status") == "SUCCESS" and "result" in entry:
            results.append(ChunkResult.model_validate(entry["result"]))

    if not results:
        print(f"  [{lecture_id}] no successful chunks; export skipped")
        return None, None

    scoring_results = [result for result in results if not result.is_fallback and result.status == ChunkStatus.SUCCESS]
    if not scoring_results:
        scoring_results = list(results)

    dumps = [result.scores.model_dump() for result in scoring_results]
    summary_dict: dict[str, dict[str, float | None]] = {}
    for category, items in dumps[0].items():
        summary_dict[category] = {}
        for item in items:
            values = [dump[category][item] for dump in dumps if dump[category].get(item) is not None]
            summary_dict[category][item] = round(sum(values) / len(values), 1) if values else None
    summary_scores = SummaryScores.model_validate(summary_dict)

    all_strengths = [text for result in results for text in (result.strengths or []) if text and "기본값" not in text]
    all_issues = [text for result in results for text in (result.issues or []) if text and "기본값" not in text]
    unique_strengths = list(dict.fromkeys(all_strengths))[:10]
    unique_issues = list(dict.fromkeys(all_issues))[:10]

    seen_evidence: dict[str, Evidence] = {}
    for result in scoring_results:
        for evidence in result.evidence or []:
            if evidence.item not in seen_evidence:
                seen_evidence[evidence.item] = evidence
    overall_evidences = list(seen_evidence.values())[:25]

    chunk_usage = reduce(
        lambda left, right: left + right,
        (result.token_usage for result in results if result.token_usage),
        TokenUsage(),
    )

    total_chunks = len(data)
    reliabilities = [result for result in results if result.reliability is not None]
    if reliabilities:
        count = len(reliabilities)
        aggregated_reliability = ReliabilityMetrics(
            evidence_pass_ratio=round(sum(item.reliability.evidence_pass_ratio for item in reliabilities) / count, 4),
            hallucination_retries=sum(item.reliability.hallucination_retries for item in reliabilities),
            avg_evidence_similarity=round(
                sum(item.reliability.avg_evidence_similarity for item in reliabilities) / count,
                2,
            ),
            score_evidence_consistency=round(
                sum(item.reliability.score_evidence_consistency for item in reliabilities) / count,
                4,
            ),
            overall_reliability_score=round(
                sum(item.reliability.overall_reliability_score for item in reliabilities) / count,
                4,
            ),
        )
    else:
        aggregated_reliability = ReliabilityMetrics(overall_reliability_score=0.0)

    failed_count = sum(1 for value in data.values() if value.get("status") == "FAILED")
    run_metadata = RunMetadata(
        prompt_version="(checkpoint export)",
        model="(checkpoint export)",
        total_chunks=total_chunks,
        scored_chunks=len(scoring_results),
        successful_chunks=len(results),
        fallback_chunks=sum(1 for result in results if result.is_fallback),
        refused_chunks=0,
        failed_chunks=failed_count,
        evidence_count_total=sum(len(result.evidence) for result in results),
        token_usage=chunk_usage,
        reliability=aggregated_reliability,
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

    output_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = llm_chunks_json_path(output_dir, lecture_id)
    summary_path = llm_json_path(output_dir, lecture_id)

    with chunks_path.open("w", encoding="utf-8") as handle:
        json.dump([result.model_dump(mode="json") for result in results], handle, ensure_ascii=False, indent=2)
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(aggregated.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)

    print(f"  [{lecture_id}] exported {len(results)}/{total_chunks} successful chunks")
    print(f"    chunks -> {chunks_path}")
    print(f"    summary -> {summary_path}")
    return chunks_path, summary_path


def find_incomplete_checkpoints(checkpoint_dir: Path, output_dir: Path) -> list[Path]:
    incomplete = []
    for checkpoint_file in sorted(checkpoint_dir.glob("*_checkpoint.json")):
        lecture_id = checkpoint_file.stem.replace("_checkpoint", "")
        summary = llm_json_path(output_dir, lecture_id)
        if not summary.exists():
            incomplete.append(checkpoint_file)
    return incomplete


def summarize_from_repo(repo: IRepository, lecture_id: str) -> None:
    results = repo.get_completed_chunks(lecture_id)
    if not results:
        print(f"  [{lecture_id}] no successful chunks")
        return

    print(f"\n{'=' * 70}")
    print(f"  {lecture_id} (via IRepository)")
    print(f"{'=' * 70}")
    print(f"  successful chunks: {len(results)}")

    item_scores: dict[str, list[int]] = defaultdict(list)
    for result in results:
        for _, items in result.scores.model_dump().items():
            if not isinstance(items, dict):
                continue
            for item_name, value in items.items():
                if value is not None:
                    item_scores[item_name].append(value)

    categories = {
        "Structure": [
            "learning_objective_intro",
            "previous_lesson_linkage",
            "explanation_sequence",
            "key_point_emphasis",
            "closing_summary",
        ],
        "Concept clarity": [
            "concept_definition",
            "analogy_example_usage",
            "prerequisite_check",
        ],
        "Practice linkage": [
            "example_appropriateness",
            "practice_transition",
            "error_handling",
        ],
        "Interaction": [
            "participation_induction",
            "question_response_sufficiency",
        ],
    }
    for label, items in categories.items():
        print(f"\n  [{label}]")
        for item in items:
            values = item_scores.get(item, [])
            if not values:
                print(f"    {item:.<40s} N/A")
            else:
                avg = sum(values) / len(values)
                print(f"    {item:.<40s} avg {avg:.1f}  (n={len(values)})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Checkpoint result viewer")
    parser.add_argument("--checkpoint", "-c", type=str, help="Specific checkpoint file path")
    parser.add_argument("--all", "-a", action="store_true", help="Summarize all checkpoints")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose per-chunk output")
    parser.add_argument("--export", "-e", action="store_true", help="Export incomplete checkpoints to output JSON")
    parser.add_argument("--repo", choices=["json", "sqlite"], default="json", help="Checkpoint repository type")
    parser.add_argument("--checkpoint-dir", type=str, default="./checkpoints")
    parser.add_argument("--output-dir", type=str, default="./data/outputs/llm")
    parser.add_argument("--lecture-id", type=str, help="When using sqlite, inspect a specific lecture_id")
    args = parser.parse_args()

    checkpoint_dir = Path(args.checkpoint_dir)
    output_dir = Path(args.output_dir)

    if args.repo == "sqlite" and args.lecture_id:
        repo = _make_repository("sqlite", args.checkpoint_dir)
        summarize_from_repo(repo, args.lecture_id)
        return

    if args.export:
        if not checkpoint_dir.exists():
            print(f"Checkpoint directory does not exist: {checkpoint_dir}", file=sys.stderr)
            sys.exit(1)

        targets = [Path(args.checkpoint)] if args.checkpoint else find_incomplete_checkpoints(checkpoint_dir, output_dir)
        if not targets:
            print("No incomplete checkpoints to export.")
            return

        print(f"Exporting {len(targets)} checkpoint(s):")
        for checkpoint_file in targets:
            export_checkpoint_to_output(checkpoint_file, output_dir)
        print("\nDone. Strengths and issues are copied from successful chunk payloads only.")
        return

    if args.checkpoint:
        checkpoint_path = Path(args.checkpoint)
        if not checkpoint_path.exists():
            print(f"File not found: {checkpoint_path}", file=sys.stderr)
            sys.exit(1)
        summarize_checkpoint(checkpoint_path, verbose=args.verbose)
        return

    if not checkpoint_dir.exists():
        print(f"Checkpoint directory does not exist: {checkpoint_dir}", file=sys.stderr)
        sys.exit(1)

    targets = sorted(checkpoint_dir.glob("*_checkpoint.json")) if args.all else find_incomplete_checkpoints(checkpoint_dir, output_dir)
    if not args.all and not targets:
        print("No incomplete checkpoints found.")
        return

    for checkpoint_file in targets:
        summarize_checkpoint(checkpoint_file, verbose=args.verbose)
    print()


if __name__ == "__main__":
    main()
