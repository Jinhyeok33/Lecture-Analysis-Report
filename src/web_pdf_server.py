"""
Frontend + PDF API 로컬 서버.

기능:
  - frontend 정적 파일 서빙
  - POST /api/report/pdf 로 리포트 PDF 생성 후 반환
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# Ensure src/ is on sys.path so sibling modules are importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from report_generator import generate_report


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
TMP_PDF_DIR = ROOT_DIR / "tmp" / "pdfs"


def _parse_metric_number(value: object, fallback: int) -> int:
    text = str(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return fallback
    try:
        return int(digits)
    except ValueError:
        return fallback


def _clamp_five(value: float) -> float:
    return max(1.0, min(5.0, value))


def _frontend_to_report_payload(data: dict) -> dict:
    scores = data.get("scores", {})
    structure = _clamp_five(_parse_metric_number(scores.get("structure", "0"), 60) / 20)
    delivery = _clamp_five(_parse_metric_number(scores.get("delivery", "0"), 60) / 20)
    interaction = _clamp_five(_parse_metric_number(scores.get("interaction", "0"), 60) / 20)
    concept = _clamp_five((structure + delivery) / 2)
    practice = _clamp_five(delivery - 0.1)

    metrics = data.get("metrics", {})
    repeat_count = _parse_metric_number(metrics.get("repeat", "5"), 5)
    complete_percent = _parse_metric_number(metrics.get("complete", "84"), 84)
    speed_wpm = _parse_metric_number(metrics.get("speed", "150"), 150)
    question_count = _parse_metric_number(metrics.get("question", "6"), 6)
    repeat_ratio = round(min(0.35, repeat_count / 40), 2)
    incomplete_ratio = round(max(0.0, min(1.0, (100 - complete_percent) / 100)), 2)

    issues = data.get("weaknesses", [])
    if not isinstance(issues, list):
        issues = []

    strengths = data.get("strengths", [])
    if not isinstance(strengths, list):
        strengths = []

    recommendations = data.get("recommendations", [])
    if not isinstance(recommendations, list):
        recommendations = []

    evidences: list[str] = []
    for index, issue in enumerate(issues):
        if index < len(recommendations):
            evidences.append(str(recommendations[index]))
        else:
            evidences.append(f"{issue} 구간의 전개를 다시 점검해 주세요.")

    course_id = str(data.get("course_id", "lecture"))
    date = str(data.get("date", "unknown"))

    return {
        "lecture_id": f"{date}_{course_id}",
        "metadata": {
            "course_id": course_id,
            "course_name": str(data.get("course_name", "-")),
            "date": date,
            "instructor": str(data.get("instructor", "-")),
            "sub_instructor": str(data.get("sub_instructor", "-")),
            "sessions": [
                {
                    "time": str(data.get("time", "-")),
                    "subject": str(data.get("subject", "-")),
                    "content": str(data.get("content", "-")),
                }
            ],
        },
        "analysis": {
            "language_quality": {
                "repeat_expressions": {
                    "이제": max(1, repeat_count),
                    "그래서": max(1, round(repeat_count * 0.8)),
                    "어쨌든": max(1, round(repeat_count * 0.4)),
                },
                "repeat_ratio": repeat_ratio,
                "incomplete_sentence_ratio": incomplete_ratio,
                "speech_style_ratio": {
                    "formal": 0.9,
                    "informal": 0.1,
                },
            },
            "concept_clarity_metrics": {
                "speech_rate_wpm": speed_wpm,
            },
            "interaction_metrics": {
                "understanding_question_count": question_count,
            },
            "summary_scores": {
                "lecture_structure": {
                    "learning_objective_intro": _clamp_five(structure + 0.2),
                    "previous_lesson_linkage": _clamp_five(structure - 0.3),
                    "explanation_sequence": _clamp_five(structure + 0.1),
                    "key_point_emphasis": _clamp_five(structure - 0.1),
                    "closing_summary": _clamp_five(structure - 0.4),
                },
                "concept_clarity": {
                    "concept_definition": _clamp_five(concept + 0.2),
                    "analogy_example_usage": _clamp_five(concept),
                    "prerequisite_check": _clamp_five(concept - 0.2),
                },
                "practice_linkage": {
                    "example_appropriateness": _clamp_five(practice + 0.2),
                    "practice_transition": _clamp_five(practice),
                    "error_handling": _clamp_five(practice - 0.2),
                },
                "interaction": {
                    "participation_induction": _clamp_five(interaction - 0.2),
                    "question_response_sufficiency": _clamp_five(interaction),
                },
            },
            "overall_strengths": strengths,
            "overall_issues": issues,
            "overall_evidences": evidences,
        },
    }


def normalize_report_payload(data: dict) -> dict:
    if "metadata" in data and "analysis" in data:
        return data
    return _frontend_to_report_payload(data)


class AppHandler(SimpleHTTPRequestHandler):
    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/report/pdf":
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        length = self.headers.get("Content-Length")
        if not length:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing Content-Length")
            return

        try:
            body = self.rfile.read(int(length))
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object.")
            normalized = normalize_report_payload(payload)
            pdf_bytes = self._build_pdf_bytes(normalized)
        except Exception as exc:
            self.send_response(HTTPStatus.BAD_REQUEST)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            error_body = {"ok": False, "error": str(exc)}
            self.wfile.write(json.dumps(error_body, ensure_ascii=False).encode("utf-8"))
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", 'attachment; filename="analysis_report.pdf"')
        self.send_header("Content-Length", str(len(pdf_bytes)))
        self.end_headers()
        self.wfile.write(pdf_bytes)

    def _build_pdf_bytes(self, payload: dict) -> bytes:
        TMP_PDF_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TMP_PDF_DIR) as temp_dir:
            temp_path = Path(temp_dir)
            input_json = temp_path / "analysis.json"
            output_pdf = temp_path / "report.pdf"
            with open(input_json, "w", encoding="utf-8") as fp:
                json.dump(payload, fp, ensure_ascii=False, indent=2)
            generate_report(str(input_json), str(output_pdf))
            return output_pdf.read_bytes()


def run_server(host: str, port: int) -> None:
    handler = partial(AppHandler, directory=str(FRONTEND_DIR))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Serving frontend: {FRONTEND_DIR}")
    print(f"Open: http://{host}:{port}/index.html")
    print("PDF API: POST /api/report/pdf")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Frontend + PDF API 로컬 서버")
    parser.add_argument("--host", default="127.0.0.1", help="바인딩 호스트")
    parser.add_argument("--port", type=int, default=5500, help="포트 번호")
    args = parser.parse_args()

    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
