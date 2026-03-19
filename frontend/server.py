from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import cgi


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.naming import (
    integrated_json_path,
    llm_chunks_json_path,
    llm_json_path,
    nlp_json_path,
    report_pdf_path,
)  # noqa: E402


METADATA_FIELDS = [
    "course_id",
    "course_name",
    "date",
    "time",
    "subject",
    "content",
    "instructor",
    "sub_instructor",
]


def decode_text_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Cannot decode metadata CSV. Use UTF-8 or CP949 encoding.")


def csv_has_matching_row(raw: bytes, date: str, course_id: str) -> bool:
    text = decode_text_bytes(raw)
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return False

    normalized = [name.strip().lower().replace("﻿", "") for name in reader.fieldnames]
    required = set(METADATA_FIELDS)
    if not required.issubset(set(normalized)):
        return False

    for row in reader:
        row_date = (row.get("date") or "").strip()
        row_course = sanitize_token((row.get("course_id") or "").strip())
        if row_date == date and row_course == course_id:
            return True
    return False


def sanitize_token(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", (value or "").strip())
    cleaned = cleaned.strip("-")
    return cleaned or "unknown"


def json_response(handler: SimpleHTTPRequestHandler, code: int, payload: dict) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def send_file(handler: SimpleHTTPRequestHandler, path: Path, content_type: str, download_name: str) -> None:
    if not path.exists():
        json_response(handler, HTTPStatus.NOT_FOUND, {"ok": False, "error": f"File not found: {path.name}"})
        return

    data = path.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
    handler.end_headers()
    handler.wfile.write(data)


def write_metadata_csv(path: Path, row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=METADATA_FIELDS)
        writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in METADATA_FIELDS})


def remove_existing_artifacts(repo_root: Path, lecture_id: str) -> None:
    candidates = [
        nlp_json_path(repo_root / "data" / "outputs" / "nlp", lecture_id),
        llm_json_path(repo_root / "data" / "outputs" / "llm", lecture_id),
        llm_chunks_json_path(repo_root / "data" / "outputs" / "llm", lecture_id),
        integrated_json_path(repo_root / "data" / "outputs" / "integrated", lecture_id),
        report_pdf_path(repo_root / "data" / "outputs" / "reports", lecture_id),
    ]
    for path in candidates:
        if path.exists():
            path.unlink()


@dataclass
class AnalysisResult:
    lecture_id: str
    analysis: dict
    chunks: list[dict]
    stdout: str
    stderr: str


def run_pipeline(repo_root: Path, lecture_id: str, transcript_path: Path, metadata_path: Path) -> AnalysisResult:
    cmd = [
        sys.executable,
        "-m",
        "src.pipeline.run_pipeline",
        "--run-nlp",
        "--run-llm",
        "--run-integrate",
        "--run-report",
        "--transcript",
        str(transcript_path),
        "--metadata",
        str(metadata_path),
        "--strict",
    ]

    proc = subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Pipeline failed (code={proc.returncode})\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    integrated_path = integrated_json_path(repo_root / "data" / "outputs" / "integrated", lecture_id)
    chunk_path = llm_chunks_json_path(repo_root / "data" / "outputs" / "llm", lecture_id)

    if not integrated_path.exists():
        raise RuntimeError(f"Integrated output missing: {integrated_path}")

    analysis = json.loads(integrated_path.read_text(encoding="utf-8-sig"))
    chunks: list[dict] = []
    if chunk_path.exists():
        chunks = json.loads(chunk_path.read_text(encoding="utf-8-sig"))

    return AnalysisResult(
        lecture_id=lecture_id,
        analysis=analysis,
        chunks=chunks,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


class EduInsightHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, repo_root: str, **kwargs):
        self.repo_root = Path(repo_root)
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            json_response(self, HTTPStatus.OK, {"ok": True})
            return

        if parsed.path == "/api/download/json":
            qs = parse_qs(parsed.query)
            lecture_id = qs.get("lecture_id", [""])[0]
            if not lecture_id:
                json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "lecture_id is required"})
                return
            path = integrated_json_path(self.repo_root / "data" / "outputs" / "integrated", lecture_id)
            send_file(self, path, "application/json; charset=utf-8", f"integrated_{lecture_id}.json")
            return

        if parsed.path == "/api/download/pdf":
            qs = parse_qs(parsed.query)
            lecture_id = qs.get("lecture_id", [""])[0]
            if not lecture_id:
                json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "lecture_id is required"})
                return
            path = report_pdf_path(self.repo_root / "data" / "outputs" / "reports", lecture_id)
            send_file(self, path, "application/pdf", f"report_{lecture_id}.pdf")
            return

        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/analyze":
            json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
            return

        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                },
            )

            required_fields = [
                "course_id",
                "course_name",
                "date",
                "time",
                "subject",
                "content",
                "instructor",
                "sub_instructor",
            ]
            values = {name: (form.getfirst(name, "") or "").strip() for name in required_fields}
            missing = [name for name, value in values.items() if not value]
            if missing:
                json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": f"Missing fields: {', '.join(missing)}"})
                return

            if "script_file" not in form:
                json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "script_file is required"})
                return

            upload = form["script_file"]
            if not getattr(upload, "file", None):
                json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Invalid script_file"})
                return

            raw = upload.file.read()
            if not raw:
                json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Uploaded txt is empty"})
                return

            sanitized_course_id = sanitize_token(values["course_id"])
            lecture_id = f"{values['date']}_{sanitized_course_id}"
            transcript_path = self.repo_root / "data" / "raw" / f"{lecture_id}.txt"
            metadata_path = self.repo_root / "data" / "metadata" / f"metadata_{lecture_id}.csv"

            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_bytes(raw)

            metadata_upload = form["metadata_csv"] if "metadata_csv" in form else None
            if metadata_upload is not None and getattr(metadata_upload, "file", None):
                metadata_raw = metadata_upload.file.read()
                if not metadata_raw:
                    json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "metadata CSV is empty"})
                    return
                if not csv_has_matching_row(metadata_raw, values["date"], sanitized_course_id):
                    json_response(
                        self,
                        HTTPStatus.BAD_REQUEST,
                        {
                            "ok": False,
                            "error": "No matching row in metadata CSV for the provided date/course_id.",
                        },
                    )
                    return
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                metadata_path.write_bytes(metadata_raw)
            else:
                metadata_row = dict(values)
                metadata_row["course_id"] = sanitized_course_id
                write_metadata_csv(metadata_path, metadata_row)

            remove_existing_artifacts(self.repo_root, lecture_id)
            result = run_pipeline(self.repo_root, lecture_id, transcript_path, metadata_path)

            payload = {
                "ok": True,
                "lecture_id": lecture_id,
                "analysis": result.analysis,
                "chunks": result.chunks,
                "downloads": {
                    "json_url": f"/api/download/json?lecture_id={quote(lecture_id)}",
                    "pdf_url": f"/api/download/pdf?lecture_id={quote(lecture_id)}",
                },
            }
            json_response(self, HTTPStatus.OK, payload)
        except Exception as exc:
            json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EduInsightAI frontend + API dev server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frontend_dir = REPO_ROOT / "frontend"
    handler = partial(EduInsightHandler, directory=str(frontend_dir), repo_root=str(REPO_ROOT))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving EduInsightAI on http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
