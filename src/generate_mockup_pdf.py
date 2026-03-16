"""
Sample analysis JSON을 기반으로 목업 PDF를 생성합니다.

기본값:
  - input:  sample/analysis_sample.json
  - output: output/pdf/analysis_mockup.pdf
"""

import argparse
from pathlib import Path

from report_generator import generate_report


def main() -> None:
    parser = argparse.ArgumentParser(description="목업 PDF 생성기")
    parser.add_argument(
        "--input",
        default=None,
        help="입력 analysis.json 경로 (기본: sample/analysis_sample.json)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="출력 PDF 경로 (기본: output/pdf/analysis_mockup.pdf)",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    input_path = Path(args.input) if args.input else root / "sample" / "analysis_sample.json"
    output_path = Path(args.output) if args.output else root / "output" / "pdf" / "analysis_mockup.pdf"

    generate_report(str(input_path), str(output_path))


if __name__ == "__main__":
    main()
