"""
결과 통합 모듈 (Result Integrator)

metadata (CSV) + NLP 분석 결과 (JSON) + LLM 분석 결과 (JSON) → analysis.json

analysis.json 출력 형식:
{
  "lecture_id": "2026-02-02_kdt-backendj-21th",
  "metadata": {
    "course_id": str,
    "course_name": str,
    "date": str,
    "instructor": str,
    "sub_instructor": str,
    "sessions": [
      {"time": str, "subject": str, "content": str},
      ...
    ]
  },
  "analysis": {
    "language_quality": {
      "repeat_expressions": {word: count},
      "repeat_ratio": float,
      "incomplete_sentence_ratio": float,
      "speech_style_ratio": {"formal": float, "informal": float}
    },
    "concept_clarity_metrics": {"speech_rate_wpm": int},
    "interaction_metrics": {"understanding_question_count": int},
    "summary_scores": {
      "lecture_structure": {item: score},
      "concept_clarity": {item: score},
      "practice_linkage": {item: score},
      "interaction": {item: score}
    },
    "overall_strengths": [str],
    "overall_issues": [str],
    "overall_evidences": [str]
  }
}
"""

import json
import csv
import argparse
from pathlib import Path


def load_metadata(csv_path: str, lecture_date: str, course_id: str) -> dict:
    """CSV에서 해당 날짜/과정의 메타데이터와 세션 목록을 로드합니다."""
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
        raise ValueError(
            f"메타데이터를 찾을 수 없습니다: date={lecture_date}, course_id={course_id}"
        )

    base_metadata["sessions"] = sessions
    return base_metadata


def merge_analyses(nlp_data: dict, llm_data: dict) -> dict:
    """NLP 출력과 LLM 출력을 하나의 analysis 객체로 병합합니다."""
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
    """세 데이터 소스를 통합하여 analysis.json을 생성합니다."""
    with open(nlp_json_path, encoding="utf-8") as f:
        nlp_data = json.load(f)
    with open(llm_json_path, encoding="utf-8") as f:
        llm_data = json.load(f)

    # lecture_id 형식: "2026-02-02_kdt-backendj-21th"
    lecture_id = nlp_data.get("lecture_id", "")
    parts = lecture_id.split("_", 1)
    lecture_date = parts[0] if len(parts) > 0 else ""
    course_id = parts[1] if len(parts) > 1 else ""

    metadata = load_metadata(metadata_csv_path, lecture_date, course_id)
    analysis = merge_analyses(nlp_data, llm_data)

    result = {
        "lecture_id": lecture_id,
        "metadata": metadata,
        "analysis": analysis,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"통합 완료: {out}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="결과 통합 모듈 (NLP + LLM + metadata → analysis.json)"
    )
    parser.add_argument("--nlp", required=True, help="NLP 분석 결과 JSON 파일 경로")
    parser.add_argument("--llm", required=True, help="LLM 분석 결과 JSON 파일 경로")
    parser.add_argument(
        "--metadata", required=True, help="강의 메타데이터 CSV 파일 경로"
    )
    parser.add_argument(
        "--output", required=True, help="출력 analysis.json 파일 경로"
    )
    args = parser.parse_args()

    integrate(args.nlp, args.llm, args.metadata, args.output)
