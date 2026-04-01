"""강의 스크립트 청크 분할 모듈."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

from src.llm_engine.core.schemas import ChunkMetadata, ParsedScript, ScriptLine

logger = logging.getLogger(__name__)

LINE_PATTERN = re.compile(r"^<(?P<timestamp>\d{2}:\d{2}:\d{2})>\s+(?P<speaker>[^:]+):\s*(?P<text>.+)$")
_HASH_SPEAKER_RE = re.compile(r"^[0-9a-f]{6,}$", re.IGNORECASE)

FALLBACK_TIMESTAMP = "00:00:00"
FALLBACK_SPEAKER = "화자미상"

BOUNDARY_SEARCH_HALF_SECONDS = 60


def _is_natural_boundary(line: ScriptLine, prev_speaker: str | None) -> bool:
    if prev_speaker is not None and line.speaker_id != prev_speaker:
        return True
    text = (line.text or "").rstrip()
    return text.endswith(".") or text.endswith("?") or text.endswith("!")


def _seconds_from_timestamp(timestamp: str) -> int:
    hour, minute, second = (int(part) for part in timestamp.split(":"))
    return hour * 3600 + minute * 60 + second


def _hhmm_from_seconds(total_seconds: int) -> str:
    hour = total_seconds // 3600
    minute = (total_seconds % 3600) // 60
    return f"{hour:02d}:{minute:02d}"


class ChunkProcessor:
    def parse_script_file(
        self,
        file_path: str | Path,
        strict_parse: bool = False,
    ) -> ParsedScript:
        """STT 스크립트 파일을 파싱한다."""
        path = Path(file_path)
        lines: List[ScriptLine] = []
        parse_failure_count = 0

        for raw_line in path.read_text(encoding="utf-8").splitlines():
            cleaned = raw_line.strip()
            if not cleaned:
                continue

            match = LINE_PATTERN.match(cleaned)
            if match:
                lines.append(
                    ScriptLine(
                        timestamp=match.group("timestamp"),
                        speaker_id=match.group("speaker").strip(),
                        text=match.group("text").strip(),
                    )
                )
            else:
                parse_failure_count += 1
                if strict_parse:
                    raise ValueError(
                        "포맷 불일치 라인 (strict_parse=True). "
                        "예상 포맷: '<HH:MM:SS> 화자: 텍스트'. "
                        f"실제 입력: '{cleaned[:80]}'"
                    )
                if lines:
                    logger.warning(
                        "file=%s stage=parse_script 포맷 불일치 라인 발견. 직전 라인에 병합합니다: '%s...'",
                        path.name,
                        cleaned[:40],
                    )
                    updated_text = lines[-1].text + f" {cleaned}"
                    lines[-1] = lines[-1].model_copy(update={"text": updated_text})
                else:
                    logger.error(
                        "file=%s stage=parse_script 첫 줄 포맷 불일치. Fallback 타임스탬프를 적용합니다: '%s...'",
                        path.name,
                        cleaned[:40],
                    )
                    lines.append(
                        ScriptLine(
                            timestamp=FALLBACK_TIMESTAMP,
                            speaker_id=FALLBACK_SPEAKER,
                            text=cleaned,
                        )
                    )

        if parse_failure_count > 0:
            logger.warning(
                "file=%s stage=parse_script parse_failure_count=%d 포맷 불일치 라인이 있습니다. "
                "스크립트 포맷을 확인하세요 (예상 포맷: '<HH:MM:SS> 화자: 텍스트').",
                path.name,
                parse_failure_count,
            )

        parsed = ParsedScript(lines=lines, parse_failure_count=parse_failure_count)
        self._validate_timestamp_order(parsed, path.name)
        return parsed

    def _validate_timestamp_order(self, parsed: ParsedScript, file_name: str) -> None:
        """타임스탬프 역전이 감지되면 경고를 남긴다."""
        prev_sec = -1
        inversion_count = 0
        for line in parsed.lines:
            sec = _seconds_from_timestamp(line.timestamp)
            if prev_sec >= 0 and sec < prev_sec - 60:
                inversion_count += 1
                if inversion_count == 1:
                    logger.warning(
                        "file=%s stage=parse_script 타임스탬프 역전 감지. 자정 이후 강의이거나 입력 포맷 오류일 수 있습니다. prev=%s current=%s",
                        file_name,
                        _hhmm_from_seconds(prev_sec),
                        line.timestamp,
                    )
            prev_sec = sec
        if inversion_count > 1:
            logger.warning(
                "file=%s stage=parse_script 타임스탬프 역전 총 %d회 발견.",
                file_name,
                inversion_count,
            )

    def create_time_based_chunks(
        self,
        parsed_data: ParsedScript,
        chunk_duration_minutes: int = 12,
        overlap_minutes: int = 2,
    ) -> List[ChunkMetadata]:
        if chunk_duration_minutes <= 0:
            raise ValueError("chunk_duration_minutes는 양수여야 합니다.")
        if overlap_minutes < 0 or overlap_minutes >= chunk_duration_minutes:
            raise ValueError("overlap_minutes는 0 이상 chunk_duration_minutes 미만이어야 합니다.")

        if not parsed_data.lines:
            return []

        chunk_duration_seconds = chunk_duration_minutes * 60
        overlap_seconds = overlap_minutes * 60
        first_second = _seconds_from_timestamp(parsed_data.lines[0].timestamp)
        seconds_per_day = 24 * 3600

        rel_lines: List[tuple[int, ScriptLine]] = []
        for line in parsed_data.lines:
            line_second = _seconds_from_timestamp(line.timestamp)
            rel = line_second - first_second
            if rel < 0:
                rel += seconds_per_day
            rel_lines.append((rel, line))

        half = BOUNDARY_SEARCH_HALF_SECONDS
        chunks_out: List[ChunkMetadata] = []
        start_sec = 0
        total_rel = rel_lines[-1][0] + 1 if rel_lines else 0

        while start_sec < total_rel:
            nominal_end = start_sec + chunk_duration_seconds
            window_low = nominal_end - half
            window_high = nominal_end + half

            end_sec = nominal_end
            found = False

            for index, (rel, line) in enumerate(rel_lines):
                if rel < window_low:
                    continue
                if rel > window_high:
                    break

                prev_speaker = rel_lines[index - 1][1].speaker_id if index > 0 else None
                if _is_natural_boundary(line, prev_speaker):
                    end_sec = rel
                    found = True
                    break

            if not found:
                for rel, _line in rel_lines:
                    if window_low <= rel <= window_high:
                        end_sec = rel
                if end_sec < window_low:
                    end_sec = min(window_high, total_rel)

            bucket_lines = [line for rel, line in rel_lines if start_sec <= rel <= end_sec]
            if not bucket_lines:
                start_sec = end_sec - overlap_seconds + 1
                if start_sec >= total_rel:
                    break
                continue

            start_second = _seconds_from_timestamp(bucket_lines[0].timestamp)
            end_second = _seconds_from_timestamp(bucket_lines[-1].timestamp)

            text_lines = [
                line.text if _HASH_SPEAKER_RE.match(line.speaker_id) else f"{line.speaker_id}: {line.text}"
                for line in bucket_lines
            ]
            text = "\n".join(text_lines)

            chunks_out.append(
                ChunkMetadata(
                    chunk_id=len(chunks_out) + 1,
                    start_time=_hhmm_from_seconds(start_second),
                    end_time=_hhmm_from_seconds(end_second),
                    text=text,
                    line_count=len(bucket_lines),
                    word_count=len(text.split()),
                )
            )

            prev_start = start_sec
            start_sec = end_sec - overlap_seconds
            if start_sec <= prev_start:
                start_sec = end_sec + 1

        return chunks_out

    def process(
        self,
        file_path: str | Path,
        chunk_duration_minutes: int = 12,
        overlap_minutes: int = 2,
        strict_parse: bool = False,
    ) -> List[ChunkMetadata]:
        parsed = self.parse_script_file(file_path, strict_parse=strict_parse)
        return self.create_time_based_chunks(
            parsed,
            chunk_duration_minutes=chunk_duration_minutes,
            overlap_minutes=overlap_minutes,
        )
