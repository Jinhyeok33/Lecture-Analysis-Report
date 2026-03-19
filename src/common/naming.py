"""Common lecture_id and artifact naming rules."""

from __future__ import annotations

from pathlib import Path


_PREFIXES = ("nlp_", "llm_", "llm_chunks_", "integrated_", "report_")


def lecture_id_from_transcript_path(path: str | Path) -> str:
    return Path(path).stem


def lecture_id_from_artifact_path(path: str | Path) -> str:
    stem = Path(path).stem
    for prefix in _PREFIXES:
        if stem.startswith(prefix):
            return stem[len(prefix) :]
    return stem


def nlp_json_filename(lecture_id: str) -> str:
    return f"nlp_{lecture_id}.json"


def llm_json_filename(lecture_id: str) -> str:
    return f"llm_{lecture_id}.json"


def llm_chunks_json_filename(lecture_id: str) -> str:
    return f"llm_chunks_{lecture_id}.json"


def integrated_json_filename(lecture_id: str) -> str:
    return f"integrated_{lecture_id}.json"


def report_pdf_filename(lecture_id: str) -> str:
    return f"report_{lecture_id}.pdf"


def nlp_json_path(output_dir: str | Path, lecture_id: str) -> Path:
    return Path(output_dir) / nlp_json_filename(lecture_id)


def llm_json_path(output_dir: str | Path, lecture_id: str) -> Path:
    return Path(output_dir) / llm_json_filename(lecture_id)


def llm_chunks_json_path(output_dir: str | Path, lecture_id: str) -> Path:
    return Path(output_dir) / llm_chunks_json_filename(lecture_id)


def integrated_json_path(output_dir: str | Path, lecture_id: str) -> Path:
    return Path(output_dir) / integrated_json_filename(lecture_id)


def report_pdf_path(output_dir: str | Path, lecture_id: str) -> Path:
    return Path(output_dir) / report_pdf_filename(lecture_id)
