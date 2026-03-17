"""Unified pipeline runner for preprocessing, NLP, LLM, integration, and report generation."""

from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.integration.result_integrator import integrate
from src.reporting.report_generator import generate_report


@dataclass
class PipelinePaths:
    repo_root: Path
    transcript: Path
    metadata_csv: Path
    nlp_output_dir: Path
    llm_output_dir: Path
    integrated_output_dir: Path
    report_output_dir: Path


@dataclass
class PipelineArtifacts:
    transcript: Path
    nlp_json: Path | None = None
    llm_json: Path | None = None
    analysis_json: Path | None = None
    report_pdf: Path | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run end-to-end lecture analysis pipeline with optional stage controls"
    )

    parser.add_argument("--transcript", type=str, help="Path to transcript txt file")
    parser.add_argument("--metadata", type=str, default="data/metadata/lecture_metadata.csv", help="Metadata CSV path")

    parser.add_argument("--run-preprocess", action="store_true", help="Run preprocessing stage")
    parser.add_argument("--run-nlp", action="store_true", help="Run NLP stage")
    parser.add_argument("--run-llm", action="store_true", help="Run LLM stage")
    parser.add_argument("--run-integrate", action="store_true", help="Run integration stage")
    parser.add_argument("--run-report", action="store_true", help="Run report generation stage")

    parser.add_argument("--nlp-json", type=str, help="Existing NLP output JSON path")
    parser.add_argument("--llm-json", type=str, help="Existing LLM output summary JSON path")
    parser.add_argument("--analysis-json", type=str, help="Existing integrated analysis JSON path")

    parser.add_argument("--max-concurrency", type=int, default=1, help="LLM chunk concurrency")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue LLM batch on per-file error")

    parser.add_argument("--validate-only", action="store_true", help="Only validate provided artifacts without running stages")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings")

    args = parser.parse_args()

    selected = [
        args.run_preprocess,
        args.run_nlp,
        args.run_llm,
        args.run_integrate,
        args.run_report,
    ]
    if not any(selected) and not args.validate_only:
        args.run_preprocess = True
        args.run_nlp = True
        args.run_llm = True
        args.run_integrate = True
        args.run_report = True

    return args


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_paths(args: argparse.Namespace) -> PipelinePaths:
    root = repo_root_from_here()

    transcript = Path(args.transcript).resolve() if args.transcript else root / "data" / "raw" / "sample.txt"
    metadata_csv = Path(args.metadata).resolve() if Path(args.metadata).is_absolute() else (root / args.metadata)

    return PipelinePaths(
        repo_root=root,
        transcript=transcript,
        metadata_csv=metadata_csv,
        nlp_output_dir=root / "data" / "outputs" / "nlp",
        llm_output_dir=root / "data" / "outputs" / "llm",
        integrated_output_dir=root / "data" / "outputs" / "integrated",
        report_output_dir=root / "data" / "outputs" / "reports",
    )


def ensure_dirs(paths: PipelinePaths) -> None:
    for p in [paths.nlp_output_dir, paths.llm_output_dir, paths.integrated_output_dir, paths.report_output_dir]:
        p.mkdir(parents=True, exist_ok=True)


def latest_matching(directory: Path, pattern: str) -> Path | None:
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def run_preprocessing(paths: PipelinePaths) -> None:
    from src.preprocessing.__main__ import main as preprocessing_main

    print("[preprocess] start")
    preprocessing_main()
    print("[preprocess] done")


def run_nlp(paths: PipelinePaths) -> Path:
    from src.nlp_engine.integrated_engine import IntegratedNLPEngine

    if not paths.transcript.exists():
        raise FileNotFoundError(f"Transcript not found: {paths.transcript}")

    lecture_id = paths.transcript.stem
    before = set(paths.nlp_output_dir.glob(f"analysis_{lecture_id}_*.json"))

    engine = IntegratedNLPEngine(output_dir=str(paths.nlp_output_dir))
    print(f"[nlp] analyze {paths.transcript.name}")
    engine.analyze_all(str(paths.transcript))

    after = set(paths.nlp_output_dir.glob(f"analysis_{lecture_id}_*.json"))
    created = sorted(after - before, key=lambda p: p.stat().st_mtime)
    out = created[-1] if created else latest_matching(paths.nlp_output_dir, f"analysis_{lecture_id}_*.json")
    if out is None:
        raise RuntimeError("NLP stage did not produce output JSON")

    print(f"[nlp] output: {out}")
    return out


def run_llm(paths: PipelinePaths, max_concurrency: int, continue_on_error: bool) -> Path:
    from src.llm_engine.application.analyzer_service import LectureAnalyzerService
    from src.llm_engine.entrypoints.batch_processor import BatchProcessor
    from src.llm_engine.infrastructure.llm.openai_adapter import OpenAIAdapter
    from src.llm_engine.infrastructure.persistence.json_repo import LocalJsonRepository

    if not paths.transcript.exists():
        raise FileNotFoundError(f"Transcript not found: {paths.transcript}")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set; cannot run LLM stage")

    provider = OpenAIAdapter()
    repository = LocalJsonRepository(base_dir=str(paths.repo_root / "checkpoints"))
    service = LectureAnalyzerService(provider, repository)
    processor = BatchProcessor(service)

    print(f"[llm] analyze {paths.transcript.name}")
    results = processor.process_files(
        transcript_files=[paths.transcript],
        output_dir=paths.llm_output_dir,
        continue_on_error=continue_on_error,
        max_concurrency=max_concurrency,
    )

    if not results:
        raise RuntimeError("LLM stage returned no results")

    first_key = next(iter(results.keys()))
    out = Path(results[first_key]["aggregated_file"])
    if not out.exists():
        raise RuntimeError(f"LLM output not found: {out}")

    print(f"[llm] output: {out}")
    return out


def run_integration(paths: PipelinePaths, nlp_json: Path, llm_json: Path) -> Path:
    if not nlp_json.exists():
        raise FileNotFoundError(f"NLP JSON not found: {nlp_json}")
    if not llm_json.exists():
        raise FileNotFoundError(f"LLM JSON not found: {llm_json}")
    if not paths.metadata_csv.exists():
        raise FileNotFoundError(f"Metadata CSV not found: {paths.metadata_csv}")

    lecture_id = read_json(nlp_json).get("lecture_id", nlp_json.stem)
    out = paths.integrated_output_dir / f"{lecture_id}_analysis.json"

    print(f"[integrate] nlp={nlp_json.name} llm={llm_json.name} metadata={paths.metadata_csv.name}")
    integrate(str(nlp_json), str(llm_json), str(paths.metadata_csv), str(out))
    print(f"[integrate] output: {out}")
    return out


def run_report(analysis_json: Path, paths: PipelinePaths) -> Path:
    if not analysis_json.exists():
        raise FileNotFoundError(f"Analysis JSON not found: {analysis_json}")

    lecture_id = read_json(analysis_json).get("lecture_id", analysis_json.stem)
    out = paths.report_output_dir / f"{lecture_id}.pdf"

    print(f"[report] input: {analysis_json.name}")
    generate_report(str(analysis_json), str(out))
    print(f"[report] output: {out}")
    return out


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def validate_nlp(path: Path) -> list[str]:
    warnings: list[str] = []
    data = read_json(path)
    required = ["lecture_id", "language_quality", "concept_clarity_metrics", "interaction_metrics"]
    for key in required:
        if key not in data:
            warnings.append(f"NLP missing key: {key}")
    return warnings


def validate_llm(path: Path) -> list[str]:
    warnings: list[str] = []
    data = read_json(path)
    agg = data.get("llm_aggregated_analysis")
    if not isinstance(agg, dict):
        warnings.append("LLM missing llm_aggregated_analysis")
        return warnings

    for key in ["summary_scores", "overall_strengths", "overall_issues", "overall_evidences"]:
        if key not in agg:
            warnings.append(f"LLM missing key: llm_aggregated_analysis.{key}")
    return warnings


def validate_integration(path: Path, metadata_csv: Path) -> list[str]:
    warnings: list[str] = []
    data = read_json(path)

    if "lecture_id" not in data:
        warnings.append("analysis missing lecture_id")
    if "metadata" not in data:
        warnings.append("analysis missing metadata")
    if "analysis" not in data:
        warnings.append("analysis missing analysis")

    lecture_id = data.get("lecture_id", "")
    if "_" in lecture_id:
        lecture_date, course_id = lecture_id.split("_", 1)
        if metadata_csv.exists():
            found = False
            with metadata_csv.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("date") == lecture_date and row.get("course_id") == course_id:
                        found = True
                        break
            if not found:
                warnings.append(f"metadata row not found for lecture_id={lecture_id}")
    else:
        warnings.append(f"lecture_id format unexpected: {lecture_id}")

    return warnings


def validate_pdf(path: Path) -> list[str]:
    warnings: list[str] = []
    if not path.exists():
        return [f"report missing: {path}"]
    if path.stat().st_size <= 1024:
        warnings.append(f"report size too small ({path.stat().st_size} bytes)")
    return warnings


def print_warnings(label: str, warnings: list[str]) -> None:
    if not warnings:
        print(f"[validate] {label}: OK")
        return
    print(f"[validate] {label}: {len(warnings)} warning(s)")
    for w in warnings:
        print(f"  - {w}")


def main() -> None:
    args = parse_args()
    paths = resolve_paths(args)
    ensure_dirs(paths)

    artifacts = PipelineArtifacts(transcript=paths.transcript)

    if args.nlp_json:
        artifacts.nlp_json = Path(args.nlp_json).resolve()
    if args.llm_json:
        artifacts.llm_json = Path(args.llm_json).resolve()
    if args.analysis_json:
        artifacts.analysis_json = Path(args.analysis_json).resolve()

    if not args.validate_only:
        if args.run_preprocess:
            run_preprocessing(paths)

        if args.run_nlp:
            artifacts.nlp_json = run_nlp(paths)

        if args.run_llm:
            artifacts.llm_json = run_llm(paths, max_concurrency=args.max_concurrency, continue_on_error=args.continue_on_error)

        if args.run_integrate:
            if artifacts.nlp_json is None:
                raise RuntimeError("NLP JSON is required for integration stage")
            if artifacts.llm_json is None:
                raise RuntimeError("LLM JSON is required for integration stage")
            artifacts.analysis_json = run_integration(paths, artifacts.nlp_json, artifacts.llm_json)

        if args.run_report:
            if artifacts.analysis_json is None:
                raise RuntimeError("analysis JSON is required for report stage")
            artifacts.report_pdf = run_report(artifacts.analysis_json, paths)

    warning_count = 0

    if artifacts.nlp_json and artifacts.nlp_json.exists():
        ws = validate_nlp(artifacts.nlp_json)
        print_warnings("NLP", ws)
        warning_count += len(ws)

    if artifacts.llm_json and artifacts.llm_json.exists():
        ws = validate_llm(artifacts.llm_json)
        print_warnings("LLM", ws)
        warning_count += len(ws)

    if artifacts.analysis_json and artifacts.analysis_json.exists():
        ws = validate_integration(artifacts.analysis_json, paths.metadata_csv)
        print_warnings("Integration", ws)
        warning_count += len(ws)

    if artifacts.report_pdf and artifacts.report_pdf.exists():
        ws = validate_pdf(artifacts.report_pdf)
        print_warnings("Report", ws)
        warning_count += len(ws)

    print("[summary]")
    print(f"  transcript: {artifacts.transcript}")
    print(f"  nlp_json: {artifacts.nlp_json}")
    print(f"  llm_json: {artifacts.llm_json}")
    print(f"  analysis_json: {artifacts.analysis_json}")
    print(f"  report_pdf: {artifacts.report_pdf}")
    print(f"  warnings: {warning_count}")

    if args.strict and warning_count > 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

