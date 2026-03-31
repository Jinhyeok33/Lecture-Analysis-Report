"""JSONL 기반 LLM 엔진 자동 테스트 실행기.

사용 예:
    python -m LLMEngine.entrypoints.test_runner
    python -m LLMEngine.entrypoints.test_runner --jsonl docs/test_cases_llm.jsonl --verbose
    python -m LLMEngine.entrypoints.test_runner --item learning_objective_intro --seed 42
    python -m LLMEngine.entrypoints.test_runner --category lecture_structure

동작 원칙:
  - 각 테스트 케이스를 chunk_id=1, total_chunks=1 단일 청크로 변환한다.
    → 위치 의존 항목(도입/마무리)이 모두 평가 대상이 되어 JSONL의 모든 케이스를 처리할 수 있다.
  - item_id 에 해당하는 청크 점수(정수 1~5)가 expected score_range 내에 있으면 통과로 판정한다.
  - is_fallback=True 인 청크는 전부 실패로 처리한다.
  - 결과는 자동으로 testcase_result/testcase_YYMMDD_HHMMSS.json (KST) 에 저장된다.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone, timedelta
import json
import logging
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from LLMEngine.core.schemas import ChunkMetadata
from LLMEngine.application.prompts import PROMPT_VERSION

logger = logging.getLogger(__name__)


# ── 헬퍼 ────────────────────────────────────────────────────────────

def _extract_score(chunk_result: Any, item_id: str) -> Optional[int]:
    """ChunkResult에서 특정 item_id 의 점수(정수)를 추출한다."""
    for cat in chunk_result.scores.model_dump().values():
        if isinstance(cat, dict) and item_id in cat:
            return cat[item_id]
    return None


def _build_chunk(tc: dict[str, Any]) -> ChunkMetadata:
    """테스트 케이스 하나를 단일 청크 메타데이터로 변환한다.

    chunk_id=1, total_chunks=1 로 설정해 시점 의존 항목(도입·마무리)도
    동시에 평가 가능하도록 한다.
    """
    text: str = tc["input"]["script_excerpt"]
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


# ── 결과 모델 ────────────────────────────────────────────────────────

@dataclass
class TestCaseResult:
    test_id: str
    title: str
    item_id: str
    category: str
    test_type: str
    expected_range: tuple[float, float]
    actual_score: Optional[int]
    passed: bool
    chunk_status: str
    elapsed_ms: int
    failure_reason: Optional[str] = None
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


# ── 핵심 실행 ────────────────────────────────────────────────────────

def run_tests(
    jsonl_path: str | Path,
    adapter: Any,
    stop_on_first_failure: bool = False,
    item_filter: list[str] | None = None,
    category_filter: list[str] | None = None,
    verbose: bool = False,
) -> list[TestCaseResult]:
    """JSONL 테스트 케이스를 순차 실행하고 결과 리스트를 반환한다.

    Args:
        jsonl_path: test_cases_llm.jsonl 파일 경로.
        adapter: ILLMProvider 구현체 (BaseLLMAdapter 서브클래스).
        stop_on_first_failure: True 이면 첫 번째 실패 시 중단한다.
        item_filter: 지정된 item_id 만 실행 (None 이면 전체).
        category_filter: 지정된 category 만 실행 (None 이면 전체).
        verbose: True 이면 실패 이유를 즉시 출력한다.
    """
    path = Path(jsonl_path)
    if not path.exists():
        raise FileNotFoundError(f"테스트 JSONL 파일을 찾을 수 없습니다: {path}")

    raw_cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                raw_cases.append(json.loads(line))

    cases = [
        c for c in raw_cases
        if (item_filter is None or c["item_id"] in item_filter)
        and (category_filter is None or c["category"] in category_filter)
    ]

    logger.info("테스트 시작: %d건 실행 (전체 %d건)", len(cases), len(raw_cases))
    results: list[TestCaseResult] = []

    for tc in cases:
        test_id: str = tc["test_id"]
        item_id: str = tc["item_id"]
        score_range = tc["expected"]["score_range"]
        expected_range: tuple[float, float] = (float(score_range[0]), float(score_range[1]))
        chunk = _build_chunk(tc)

        t0 = time.perf_counter()
        actual_score: Optional[int] = None
        chunk_status = "UNKNOWN"
        failure_reason: Optional[str] = None
        passed = False

        try:
            chunk_result = adapter.analyze_chunk(chunk)
            chunk_status = chunk_result.status.value

            if chunk_result.is_fallback:
                failure_reason = f"Fallback 사용됨: {chunk_result.failure_reason}"
                passed = False
            else:
                actual_score = _extract_score(chunk_result, item_id)
                if actual_score is None:
                    failure_reason = (
                        f"'{item_id}' 점수가 null — 위치 의존 항목이 잘못된 청크 위치에서 평가된 경우 확인 필요"
                    )
                    passed = False
                else:
                    passed = expected_range[0] <= actual_score <= expected_range[1]
                    if not passed:
                        failure_reason = (
                            f"점수 범위 불일치: 실제={actual_score}점 "
                            f"(기대: {expected_range[0]}~{expected_range[1]})"
                        )

        except Exception as exc:
            chunk_status = "ERROR"
            failure_reason = f"{type(exc).__name__}: {exc}"
            passed = False

        elapsed = int((time.perf_counter() - t0) * 1000)
        result = TestCaseResult(
            test_id=test_id,
            title=tc["title"],
            item_id=item_id,
            category=tc["category"],
            test_type=tc["test_type"],
            expected_range=expected_range,
            actual_score=actual_score,
            passed=passed,
            chunk_status=chunk_status,
            elapsed_ms=elapsed,
            failure_reason=failure_reason,
            notes=tc.get("notes", ""),
        )
        results.append(result)

        icon = "PASS" if passed else "FAIL"
        log_fn = logger.info if passed else logger.warning
        log_fn(
            "[%s] %s | %s | %s | 기대:[%.1f~%.1f] 실제:%s | %dms",
            icon, test_id, tc["title"], tc["test_type"],
            expected_range[0], expected_range[1],
            actual_score if actual_score is not None else "null",
            elapsed,
        )
        if not passed and verbose and failure_reason:
            logger.warning("     => %s", failure_reason)

        if stop_on_first_failure and not passed:
            logger.warning("stop_on_first_failure=True — 이후 케이스 중단")
            break

    return results


# ── 리포트 출력 ──────────────────────────────────────────────────────

def print_report(results: list[TestCaseResult]) -> None:
    """테스트 결과를 카테고리별로 요약 출력한다."""
    total = len(results)
    passed_count = sum(1 for r in results if r.passed)
    failed_count = total - passed_count

    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  LLM 엔진 테스트 결과   통과: {passed_count}/{total}   실패: {failed_count}")
    print(sep)

    by_cat: dict[str, list[TestCaseResult]] = defaultdict(list)
    for r in results:
        by_cat[r.category].append(r)

    for cat, cat_results in sorted(by_cat.items()):
        cat_pass = sum(1 for r in cat_results if r.passed)
        print(f"\n  [{cat}]  {cat_pass}/{len(cat_results)}")
        for r in cat_results:
            icon = "O" if r.passed else "X"
            score_str = str(r.actual_score) if r.actual_score is not None else "null"
            exp_str = f"[{r.expected_range[0]:.1f}~{r.expected_range[1]:.1f}]"
            print(
                f"    {icon}  {r.test_id:<14}  {r.test_type:<10}  "
                f"기대:{exp_str}  실제:{score_str:>4}   {r.title}"
            )
            if not r.passed and r.failure_reason:
                print(f"          => {r.failure_reason}")

    if failed_count > 0:
        print(f"\n{'─' * 70}")
        print("  실패 케이스 요약")
        for r in results:
            if not r.passed:
                print(f"  {r.test_id}  {r.title}")
                if r.failure_reason:
                    print(f"    → {r.failure_reason}")

    print(f"\n{sep}\n")


# ── CLI 엔트리포인트 ─────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="LLM 엔진 JSONL 자동 테스트 실행기",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--jsonl", "-j",
        default="docs/test_cases_llm.jsonl",
        help="테스트 케이스 JSONL 파일 경로",
    )
    p.add_argument(
        "--item", "-i",
        nargs="*",
        metavar="ITEM_ID",
        help="실행할 item_id 목록 (미지정 시 전체). 예: --item learning_objective_intro closing_summary",
    )
    p.add_argument(
        "--category", "-c",
        nargs="*",
        metavar="CATEGORY",
        help="실행할 category 목록 (미지정 시 전체). 예: --category lecture_structure interaction",
    )
    p.add_argument(
        "--stop-on-fail",
        action="store_true",
        help="첫 번째 실패 시 이후 케이스를 중단한다",
    )
    p.add_argument("--verbose", "-v", action="store_true", help="실패 이유를 즉시 상세 출력")
    p.add_argument(
        "--model",
        default=None,
        help="사용할 LLM 모델명 (미지정 시 환경변수 LLM_MODEL 또는 gpt-4o-2024-08-06)",
    )
    p.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="LLM temperature (미지정 시 config 기본값 0.5)",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="재현성용 seed (OpenAI 전용; 미지정 시 비결정적)",
    )
    p.add_argument(
        "--output", "-o",
        default=None,
        metavar="FILE",
        help="JSON 형태로 결과를 저장할 파일 경로",
    )
    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()

    import os
    from LLMEngine.core.logging_config import setup_logging

    use_json = os.getenv("LLM_LOG_FORMAT", "").strip().lower() == "json"
    setup_logging(
        level="DEBUG" if args.verbose else "INFO",
        json_format=use_json,
    )

    from LLMEngine.core.config import LLMEngineConfig
    from LLMEngine.infrastructure.llm.openai_adapter import OpenAIAdapter

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

    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    timestamp = now_kst.strftime("%y%m%d_%H%M%S")

    if args.output:
        out_path = Path(args.output)
    else:
        out_dir = Path("testcase_result")
        out_path = out_dir / f"testcase_{timestamp}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = len(results)
    passed_count = sum(1 for r in results if r.passed)
    failed_count = total - passed_count

    save_payload = {
        "run_timestamp_kst": now_kst.isoformat(),
        "prompt_version": PROMPT_VERSION,
        "total": total,
        "passed": passed_count,
        "failed": failed_count,
        "results": [r.to_dict() for r in results],
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(save_payload, f, ensure_ascii=False, indent=2)
    logger.info("결과 자동 저장 완료: %s", out_path)

    sys.exit(1 if failed_count > 0 else 0)
