from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
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

STAGE_SEQUENCE = ("nlp", "llm", "integrate", "report")
STAGE_MESSAGES = {
    "queued": "분석 요청 준비 중…",
    "nlp": "NLP 분석 중…",
    "llm": "LLM 분석 중…",
    "integrate": "통합 중…",
    "report": "리포트 생성 중…",
    "done": "분석 완료",
    "error": "분석 중 오류가 발생했습니다.",
}


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


def stage_to_step_index(stage: str) -> int | None:
    if stage in STAGE_SEQUENCE:
        return STAGE_SEQUENCE.index(stage)
    if stage == "done":
        return len(STAGE_SEQUENCE) - 1
    return None


def infer_stage_from_log(line: str) -> str | None:
    stripped = (line or "").strip().lower()
    if stripped.startswith("[nlp]"):
        return "nlp"
    if stripped.startswith("[llm]"):
        return "llm"
    if stripped.startswith("[integrate]"):
        return "integrate"
    if stripped.startswith("[report]"):
        return "report"
    return None


def summarize_pipeline_failure(returncode: int, lines: list[str]) -> str:
    candidates = [line.strip() for line in lines if line and line.strip()]
    for line in reversed(candidates):
        lowered = line.lower()
        if "openai_api_key" in lowered or "not set" in lowered:
            return line
        if "error" in lowered or "failed" in lowered or "missing" in lowered:
            return line
    if candidates:
        return candidates[-1]
    return f"Pipeline failed (code={returncode})"


def prepare_analysis_request(handler: SimpleHTTPRequestHandler, repo_root: Path) -> PreparedAnalysis:
    form = cgi.FieldStorage(
        fp=handler.rfile,
        headers=handler.headers,
        environ={
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": handler.headers.get("Content-Type", ""),
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
        raise ValueError(f"Missing fields: {', '.join(missing)}")

    if "script_file" not in form:
        raise ValueError("script_file is required")

    upload = form["script_file"]
    if not getattr(upload, "file", None):
        raise ValueError("Invalid script_file")

    raw = upload.file.read()
    if not raw:
        raise ValueError("Uploaded txt is empty")

    sanitized_course_id = sanitize_token(values["course_id"])
    lecture_id = f"{values['date']}_{sanitized_course_id}"
    transcript_path = repo_root / "data" / "raw" / f"{lecture_id}.txt"
    metadata_path = repo_root / "data" / "metadata" / f"metadata_{lecture_id}.csv"

    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    transcript_path.write_bytes(raw)

    metadata_upload = form["metadata_csv"] if "metadata_csv" in form else None
    if metadata_upload is not None and getattr(metadata_upload, "file", None):
        metadata_raw = metadata_upload.file.read()
        if not metadata_raw:
            raise ValueError("metadata CSV is empty")
        if not csv_has_matching_row(metadata_raw, values["date"], sanitized_course_id):
            raise ValueError("No matching row in metadata CSV for the provided date/course_id.")
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_bytes(metadata_raw)
    else:
        metadata_row = dict(values)
        metadata_row["course_id"] = sanitized_course_id
        write_metadata_csv(metadata_path, metadata_row)

    return PreparedAnalysis(
        lecture_id=lecture_id,
        transcript_path=transcript_path,
        metadata_path=metadata_path,
    )


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


@dataclass
class PreparedAnalysis:
    lecture_id: str
    transcript_path: Path
    metadata_path: Path


@dataclass
class AnalysisJob:
    job_id: str
    lecture_id: str
    state: str = "queued"
    stage: str = "queued"
    message: str = STAGE_MESSAGES["queued"]
    error: str = ""
    result: dict | None = None
    stdout: str = ""
    stderr: str = ""
    updated_at: float = field(default_factory=time.time)


class AnalysisJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, AnalysisJob] = {}
        self._lock = threading.Lock()

    def create(self, lecture_id: str) -> AnalysisJob:
        job = AnalysisJob(job_id=uuid.uuid4().hex, lecture_id=lecture_id)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def update(
        self,
        job_id: str,
        *,
        state: str | None = None,
        stage: str | None = None,
        message: str | None = None,
        error: str | None = None,
        result: dict | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if state is not None:
                job.state = state
            if stage is not None:
                job.stage = stage
            if message is not None:
                job.message = message
            if error is not None:
                job.error = error
            if result is not None:
                job.result = result
            if stdout is not None:
                job.stdout = stdout
            if stderr is not None:
                job.stderr = stderr
            job.updated_at = time.time()

    def snapshot(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            payload = {
                "ok": True,
                "job_id": job.job_id,
                "lecture_id": job.lecture_id,
                "state": job.state,
                "stage": job.stage,
                "step_index": stage_to_step_index(job.stage),
                "message": job.message,
                "updated_at": job.updated_at,
            }
            if job.error:
                payload["error"] = job.error
            if job.state == "done" and job.result is not None:
                payload["result"] = job.result
            return payload


JOB_STORE = AnalysisJobStore()


def run_pipeline(
    repo_root: Path,
    lecture_id: str,
    transcript_path: Path,
    metadata_path: Path,
    on_stage_change: Callable[[str, str], None] | None = None,
) -> AnalysisResult:
    cmd = [
        sys.executable,
        "-u",
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

    proc = subprocess.Popen(
        cmd,
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    lines: list[str] = []
    current_stage = ""

    if proc.stdout is not None:
        for raw_line in proc.stdout:
            lines.append(raw_line)
            next_stage = infer_stage_from_log(raw_line)
            if next_stage and next_stage != current_stage:
                current_stage = next_stage
                if on_stage_change is not None:
                    on_stage_change(next_stage, STAGE_MESSAGES[next_stage])

    returncode = proc.wait()
    stdout = "".join(lines)
    stderr = ""
    if returncode != 0:
        raise RuntimeError(summarize_pipeline_failure(returncode, lines))

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
        stdout=stdout,
        stderr=stderr,
    )


def build_analysis_payload(result: AnalysisResult) -> dict:
    return {
        "ok": True,
        "lecture_id": result.lecture_id,
        "analysis": result.analysis,
        "chunks": result.chunks,
        "downloads": {
            "json_url": f"/api/download/json?lecture_id={quote(result.lecture_id)}",
            "pdf_url": f"/api/download/pdf?lecture_id={quote(result.lecture_id)}",
        },
    }


def execute_analysis_job(
    job_id: str,
    repo_root: Path,
    lecture_id: str,
    transcript_path: Path,
    metadata_path: Path,
) -> None:
    JOB_STORE.update(job_id, state="running", stage="nlp", message=STAGE_MESSAGES["nlp"], error="")
    try:
        remove_existing_artifacts(repo_root, lecture_id)
        result = run_pipeline(
            repo_root,
            lecture_id,
            transcript_path,
            metadata_path,
            on_stage_change=lambda stage, message: JOB_STORE.update(
                job_id,
                state="running",
                stage=stage,
                message=message,
            ),
        )
        JOB_STORE.update(
            job_id,
            state="done",
            stage="done",
            message=STAGE_MESSAGES["done"],
            result=build_analysis_payload(result),
            stdout=result.stdout,
            stderr=result.stderr,
            error="",
        )
    except Exception as exc:
        JOB_STORE.update(
            job_id,
            state="error",
            stage="error",
            message=STAGE_MESSAGES["error"],
            error=str(exc).strip() or "분석 중 오류가 발생했습니다.",
        )


class EduInsightHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, repo_root: str, **kwargs):
        self.repo_root = Path(repo_root)
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            json_response(self, HTTPStatus.OK, {"ok": True})
            return

        if parsed.path == "/api/analyze/status":
            qs = parse_qs(parsed.query)
            job_id = qs.get("job_id", [""])[0]
            if not job_id:
                json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": "job_id is required"})
                return
            snapshot = JOB_STORE.snapshot(job_id)
            if snapshot is None:
                json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "Analysis job not found"})
                return
            json_response(self, HTTPStatus.OK, snapshot)
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
        if parsed.path not in {"/api/analyze", "/api/analyze/start"}:
            json_response(self, HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
            return

        try:
            prepared = prepare_analysis_request(self, self.repo_root)
            job = JOB_STORE.create(prepared.lecture_id)
            thread = threading.Thread(
                target=execute_analysis_job,
                args=(
                    job.job_id,
                    self.repo_root,
                    prepared.lecture_id,
                    prepared.transcript_path,
                    prepared.metadata_path,
                ),
                daemon=True,
            )
            thread.start()

            payload = {
                "ok": True,
                "job_id": job.job_id,
                "lecture_id": prepared.lecture_id,
                "state": "queued",
                "stage": "queued",
                "step_index": stage_to_step_index("queued"),
                "message": STAGE_MESSAGES["queued"],
            }
            json_response(self, HTTPStatus.ACCEPTED, payload)
        except ValueError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
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
