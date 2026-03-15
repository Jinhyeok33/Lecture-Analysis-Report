"""강의 스크립트 청크 분할 모듈."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List

from core.schemas import ChunkMetadata, ParsedScript, ScriptLine

logger = logging.getLogger(__name__)

LINE_PATTERN = re.compile(r"^<(?P<timestamp>\d{2}:\d{2}:\d{2})>\s+(?P<speaker>[^:]+):\s*(?P<text>.+)$")

FALLBACK_TIMESTAMP = "00:00:00"
FALLBACK_SPEAKER = "화자미상"

BOUNDARY_SEARCH_HALF_SECONDS = 60

def _is_natural_boundary(line: ScriptLine, prev_speaker: str | None) -> bool:
    if prev_speaker is not None and line.speaker_id != prev_speaker:
        return True
    t = (line.text or "").rstrip()
    return t.endswith(".") or t.endswith("?") or t.endswith("!")

def _seconds_from_timestamp(timestamp: str) -> int:
    hour, minute, second = (int(part) for part in timestamp.split(":"))
    return hour * 3600 + minute * 60 + second

def _hhmm_from_seconds(total_seconds: int) -> str:
    hour = total_seconds // 3600
    minute = (total_seconds % 3600) // 60
    return f"{hour:02d}:{minute:02d}"

class ChunkProcessor:
    def parse_script_file(self, file_path: str | Path) -> ParsedScript:
        path = Path(file_path)
        lines: List[ScriptLine] = []

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
                if lines:
                    logger.debug("STT 파싱 실패. 직전 라인에 텍스트를 병합합니다: %s...", cleaned[:30])
                    updated_text = lines[-1].text + f" {cleaned}"
                    lines[-1] = lines[-1].model_copy(update={"text": updated_text})
                else:
                    logger.error("스크립트 첫 줄 파싱 실패. Fallback 타임스탬프를 적용합니다.")
                    lines.append(
                        ScriptLine(
                            timestamp=FALLBACK_TIMESTAMP,
                            speaker_id=FALLBACK_SPEAKER,
                            text=cleaned,
                        )
                    )

        return ParsedScript(lines=lines)

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
        SECONDS_PER_DAY = 24 * 3600
        
        rel_lines: List[tuple[int, ScriptLine]] = []
        for line in parsed_data.lines:
            line_second = _seconds_from_timestamp(line.timestamp)
            rel = line_second - first_second
            if rel < 0:
                rel += SECONDS_PER_DAY
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
            
            for i, (rel, line) in enumerate(rel_lines):
                if rel < window_low:
                    continue
                if rel > window_high:
                    break
                    
                prev_s = rel_lines[i - 1][1].speaker_id if i > 0 else None
                
                if _is_natural_boundary(line, prev_s):
                    end_sec = rel
                    found = True
                    break
                    
            if not found:
                for rel, line in rel_lines:
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
            
            text_lines = [f"{line.speaker_id}: {line.text}" for line in bucket_lines]
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
            
            start_sec = end_sec - overlap_seconds
            if start_sec <= 0:
                start_sec = end_sec + 1

        return chunks_out

    def process(
        self,
        file_path: str | Path,
        chunk_duration_minutes: int = 12,
        overlap_minutes: int = 2,
    ) -> List[ChunkMetadata]:
        parsed = self.parse_script_file(file_path)
        return self.create_time_based_chunks(
            parsed,
            chunk_duration_minutes=chunk_duration_minutes,
            overlap_minutes=overlap_minutes,
        )