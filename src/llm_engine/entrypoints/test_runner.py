"""JSONL-based LLM engine test runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.llm_engine.application.prompts import PROMPT_VERSION
from src.llm_engine.core.schemas import ChunkMetadata

logger = logging.getLogger(__name__)


def _extract_score(chunk_result: Any, item_id: str) -> int | None:
    for category in chunk_result.scores.model_dump().values():
        if isinstance(category, dict) and item_id in category:
            return category[item_id]
    return None


def _build_chunk(test_case: dict[str, Any]) -> ChunkMetadata:
    text: str = test_case["input"]["script_excerpt"]
    words = text.split()
    return ChunkMetadata(
        chunk_id=1,
        start_time="00:00",
        end_time="00:10",
        text=text,
        line_count=max(1, text.count("\n") + 1),
        word_count=max(1, len(words)),
        previous_chunk_tail=None,
        total_chunks=1,
    )


@dataclass
class TestCaseResult:
    test_id: str
    title: str
    item_id: str
    category: str
    test_type: str
    expected_range: tuple[float, float]
    actual_score: int | None
    passed: bool
    chunk_status: str
    elapsed_ms: int
    failure_reason: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_id,
            "title": self.title,
            "item_id": self.item_id,
            "category": self.category,
            "test_type": self.test_type,
            "expected_range": list(self.expected_range),
            "actual_score": self.actual_score,
            "passed": self.passed,
            "chunk_status": self.chunk_status,
            "elapsed_ms": self.elapsed_ms,
            "failure_reason": self.failure_reason,
            "notes": self.notes,
        }


def run_tests(
    jsonl_path: str | Path,
    adapter: Any,
    stop_on_first_failure: bool = False,
    item_filter: list[str] | None = None,
    category_filter: list[str] | None = None,
    verbose: bool = False,
) -> list[TestCaseResult]:
    path = Path(jsonl_path)
    if not path.exists():
        raise FileNotFoundError(f"Test JSONL not found: {path}")

    raw_cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                raw_cases.append(json.loads(line))

    cases = [
        case
        for case in raw_cases
        if (item_filter is None or case["item_id"] in item_filter)
        and (category_filter is None or case["category"] in category_filter)
    ]

    logger.info("Running %d test cases (from %d total)", len(cases), len(raw_cases))
    results: list[TestCaseResult] = []

    for case in cases:
        test_id = case["test_id"]
        item_id = case["item_id"]
        lower, upper = case["expected"]["score_range"]
        expected_range = (float(lower), float(upper))
        chunk = _build_chunk(case)

        started = time.perf_counter()
        actual_score: int | None = None
        chunk_status = "UNKNOWN"
        failure_reason: str | None = None
        passed = False

        try:
            chunk_result = adapter.analyze_chunk(chunk)
            chunk_status = chunk_result.status.value

            if chunk_result.is_fallback:
                failure_reason = f"Fallback used: {chunk_result.failure_reason}"
            else:
                actual_score = _extract_score(chunk_result, item_id)
                if actual_score is None:
                    failure_reason = f"'{item_id}' score is null"
                else:
                    passed = expected_range[0] <= actual_score <= expected_range[1]
                    if not passed:
                        failure_reason = (
                            f"Score mismatch: actual={actual_score}, expected={expected_range[0]}~{expected_range[1]}"
                        )
        except Exception as exc:
            chunk_status = "ERROR"
            failure_reason = f"{type(exc).__name__}: {exc}"

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        result = TestCaseResult(
            test_id=test_id,
            title=case["title"],
            item_id=item_id,
            category=case["category"],
            test_type=case["test_type"],
            expected_range=expected_range,
            actual_score=actual_score,
            passed=passed,
            chunk_status=chunk_status,
            elapsed_ms=elapsed_ms,
            failure_reason=failure_reason,
            notes=case.get("notes", ""),
        )
        results.append(result)

        logger_method = logger.info if passed else logger.warning
        logger_method(
            "[%s] %s | %s | expected=[%.1f~%.1f] actual=%s | %dms",
            "PASS" if passed else "FAIL",
            test_id,
            case["title"],
            expected_range[0],
            expected_range[1],
            actual_score if actual_score is not None else "null",
            elapsed_ms,
        )
        if not passed and verbose and failure_reason:
            logger.warning(" => %s", failure_reason)
        if stop_on_first_failure and not passed:
            logger.warning("Stopping after first failure")
            break

    return results


def print_report(results: list[TestCaseResult]) -> None:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    failed = total - passed

    separator = "=" * 70
    print(f"\n{separator}")
    print(f"  LLM engine tests   passed: {passed}/{total}   failed: {failed}")
    print(separator)

    by_category: dict[str, list[TestCaseResult]] = defaultdict(list)
    for result in results:
        by_category[result.category].append(result)

    for category, category_results in sorted(by_category.items()):
        category_passed = sum(1 for result in category_results if result.passed)
        print(f"\n  [{category}]  {category_passed}/{len(category_results)}")
        for result in category_results:
            icon = "O" if result.passed else "X"
            score_text = str(result.actual_score) if result.actual_score is not None else "null"
            expected_text = f"[{result.expected_range[0]:.1f}~{result.expected_range[1]:.1f}]"
            print(
                f"    {icon}  {result.test_id:<14}  {result.test_type:<10}  "
                f"expected:{expected_text}  actual:{score_text:>4}   {result.title}"
            )
            if not result.passed and result.failure_reason:
                print(f"          => {result.failure_reason}")

    if failed > 0:
        print(f"\n{'-' * 70}")
        print("  Failed cases")
        for result in results:
            if not result.passed:
                print(f"  {result.test_id}  {result.title}")
                if result.failure_reason:
                    print(f"    -> {result.failure_reason}")

    print(f"\n{separator}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run JSONL-based LLM engine tests",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--jsonl", "-j", default="docs/test_cases_llm.jsonl", help="Test case JSONL path")
    parser.add_argument("--item", "-i", nargs="*", metavar="ITEM_ID", help="Filter by item id")
    parser.add_argument("--category", "-c", nargs="*", metavar="CATEGORY", help="Filter by category")
    parser.add_argument("--stop-on-fail", action="store_true", help="Stop after first failure")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed failure reasons")
    parser.add_argument("--model", default=None, help="LLM model override")
    parser.add_argument("--temperature", type=float, default=None, help="Temperature override")
    parser.add_argument("--seed", type=int, default=None, help="Seed override")
    parser.add_argument("--output", "-o", default=None, metavar="FILE", help="Where to save JSON results")
    return parser


if __name__ == "__main__":
    args = _build_parser().parse_args()

    import os

    from src.llm_engine.core.config import LLMEngineConfig
    from src.llm_engine.core.logging_config import setup_logging
    from src.llm_engine.infrastructure.llm.openai_adapter import OpenAIAdapter

    use_json = os.getenv("LLM_LOG_FORMAT", "").strip().lower() == "json"
    setup_logging(level="DEBUG" if args.verbose else "INFO", json_format=use_json)

    config = LLMEngineConfig.from_env()
    adapter = OpenAIAdapter(
        model=args.model or config.model,
        max_retries=config.max_retries,
        retry_base_delay=config.retry_base_delay,
        api_timeout_s=config.api_timeout_s,
        max_completion_tokens=config.max_completion_tokens,
        temperature=args.temperature if args.temperature is not None else config.temperature,
        seed=args.seed if args.seed is not None else config.seed,
    )

    results = run_tests(
        jsonl_path=args.jsonl,
        adapter=adapter,
        stop_on_first_failure=args.stop_on_fail,
        item_filter=args.item,
        category_filter=args.category,
        verbose=args.verbose,
    )
    print_report(results)

    kst = timezone(timedelta(hours=9))
    timestamp = datetime.now(kst).strftime("%y%m%d_%H%M%S")
    out_path = Path(args.output) if args.output else Path("testcase_result") / f"testcase_{timestamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = len(results)
    passed = sum(1 for result in results if result.passed)
    failed = total - passed
    payload = {
        "run_timestamp_kst": datetime.now(kst).isoformat(),
        "prompt_version": PROMPT_VERSION,
        "total": total,
        "passed": passed,
        "failed": failed,
        "results": [result.to_dict() for result in results],
    }
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    logger.info("Saved test results to %s", out_path)

    sys.exit(1 if failed > 0 else 0)
