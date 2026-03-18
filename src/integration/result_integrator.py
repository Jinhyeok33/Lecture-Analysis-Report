"""Result integrator: metadata + NLP JSON + LLM JSON -> integrated JSON."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from src.common.naming import lecture_id_from_artifact_path


def load_metadata(csv_path: str, lecture_date: str, course_id: str) -> dict:
    sessions = []
    base_metadata = {}

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["date"] == lecture_date and row["course_id"] == course_id:
                if not base_metadata:
                    base_metadata = {
                        "course_id": row["course_id"],
                        "course_name": row["course_name"],
                        "date": row["date"],
                        "instructor": row["instructor"],
                        "sub_instructor": row["sub_instructor"],
                    }
                sessions.append(
                    {
                        "time": row["time"],
                        "subject": row["subject"],
                        "content": row["content"],
                    }
                )

    if not base_metadata:
        raise ValueError(f"메타데이터를 찾을 수 없습니다: date={lecture_date}, course_id={course_id}")

    base_metadata["sessions"] = sessions
    return base_metadata


def merge_analyses(nlp_data: dict, llm_data: dict) -> dict:
    llm_agg = llm_data.get("llm_aggregated_analysis", {})
    return {
        "language_quality": nlp_data.get("language_quality", {}),
        "concept_clarity_metrics": nlp_data.get("concept_clarity_metrics", {}),
        "interaction_metrics": nlp_data.get("interaction_metrics", {}),
        "summary_scores": llm_agg.get("summary_scores", {}),
        "overall_strengths": llm_agg.get("overall_strengths", []),
        "overall_issues": llm_agg.get("overall_issues", []),
        "overall_evidences": llm_agg.get("overall_evidences", []),
    }


def integrate(
    nlp_json_path: str,
    llm_json_path: str,
    metadata_csv_path: str,
    output_path: str,
) -> dict:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 이미 통합 결과가 있으면 바로 재사용
    if out.exists():
        with open(out, encoding="utf-8-sig") as f:
            return json.load(f)

    with open(nlp_json_path, encoding="utf-8-sig") as f:
        nlp_data = json.load(f)
    with open(llm_json_path, encoding="utf-8-sig") as f:
        llm_data = json.load(f)

    lecture_id = nlp_data.get("lecture_id") or lecture_id_from_artifact_path(nlp_json_path)
    lecture_date, course_id = lecture_id.split("_", 1)

    metadata = load_metadata(metadata_csv_path, lecture_date, course_id)
    analysis = merge_analyses(nlp_data, llm_data)

    result = {
        "lecture_id": lecture_id,
        "metadata": metadata,
        "analysis": analysis,
    }

    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"통합 완료: {out}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="결과 통합 모듈 (NLP + LLM + metadata -> integrated JSON)")
    parser.add_argument("--nlp", required=True, help="NLP 분석 결과 JSON 파일 경로")
    parser.add_argument("--llm", required=True, help="LLM 분석 결과 JSON 파일 경로")
    parser.add_argument("--metadata", required=True, help="강의 메타데이터 CSV 파일 경로")
    parser.add_argument("--output", required=True, help="출력 integrated JSON 파일 경로")
    args = parser.parse_args()

    integrate(args.nlp, args.llm, args.metadata, args.output)
