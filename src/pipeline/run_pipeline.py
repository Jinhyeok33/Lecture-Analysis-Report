"""Run integration and PDF generation pipeline for a single lecture."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.integration.result_integrator import integrate
from src.reporting.report_generator import generate_report


def run_pipeline(
    nlp_json: str,
    llm_json: str,
    metadata_csv: str,
    analysis_json_out: str,
    report_pdf_out: str,
) -> None:
    integrate(
        nlp_json_path=nlp_json,
        llm_json_path=llm_json,
        metadata_csv_path=metadata_csv,
        output_path=analysis_json_out,
    )
    generate_report(analysis_json_out, report_pdf_out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run pipeline: NLP JSON + LLM JSON + metadata CSV -> analysis JSON -> PDF"
    )
    parser.add_argument("--nlp", required=True, help="Path to NLP output JSON")
    parser.add_argument("--llm", required=True, help="Path to LLM output JSON")
    parser.add_argument("--metadata", required=True, help="Path to metadata CSV")
    parser.add_argument("--analysis-out", required=True, help="Output path for integrated analysis JSON")
    parser.add_argument("--report-out", required=True, help="Output path for report PDF")
    args = parser.parse_args()

    Path(args.analysis_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
    run_pipeline(
        nlp_json=args.nlp,
        llm_json=args.llm,
        metadata_csv=args.metadata,
        analysis_json_out=args.analysis_out,
        report_pdf_out=args.report_out,
    )
