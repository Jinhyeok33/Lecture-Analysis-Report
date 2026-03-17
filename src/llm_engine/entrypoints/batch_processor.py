"""여러 강의 스크립트 파일을 배치 처리하는 모듈 (Entrypoint)."""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import re
import time
from pathlib import Path
from typing import Dict

from src.llm_engine.core.schemas import AggregatedResult, ChunkResult
from src.llm_engine.application.analyzer_service import LectureAnalyzerService

def normalize_lecture_id(stem: str) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(.*)$", stem)
    if m:
        return f"{m.group(1)[2:]}{m.group(2)}{m.group(3)}{m.group(4)}"
    return stem

def get_lecture_id_with_run_number(output_dir: Path, base_lecture_id: str) -> str:
    """동일한 base_lecture_id가 있으면 _01, _02, _03 형태로 두 자리 숫자를 패딩하여 넘버링합니다."""
    if not output_dir.exists():
        return f"{base_lecture_id}_01"
        
    existing = list(output_dir.glob(f"{base_lecture_id}*_summary.json"))
    if not existing:
        return f"{base_lecture_id}_01"
        
    max_run = 0
    for p in existing:
        # 두 자리 숫자로 매칭
        m = re.search(r"_(\d{2})_summary\.json$", p.name)
        if m:
            run_num = int(m.group(1))
            max_run = max(max_run, run_num)
        elif p.name == f"{base_lecture_id}_summary.json":
            # 이전 테스트 때 (run, _1,,) 번호 없이 저장된 구버전 파일이 있다면 1로 간주
            max_run = max(max_run, 1)
            
    return f"{base_lecture_id}_{max_run + 1:02d}"

class BatchProcessor:
    def __init__(self, analyzer_service: LectureAnalyzerService) -> None:
        self.service = analyzer_service

    def process_files(
        self,
        transcript_files: list[str | Path],
        output_dir: str | Path,
        continue_on_error: bool = True,
        max_concurrency: int = 1,
    ) -> Dict[str, dict]:
        results: Dict[str, dict] = {}
        errors: Dict[str, str] = {}
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        batch_start_time = time.perf_counter()

        for file_path in transcript_files:
            path = Path(file_path)
            base_id = normalize_lecture_id(path.stem)
            lecture_id = get_lecture_id_with_run_number(out_path, base_id)

            file_start_time = time.perf_counter()
            try:
                print(f"시작: {lecture_id} (파일: {path.name})")
                
                chunk_results, aggregated_result = self.service.process_lecture(
                    lecture_id, path, max_concurrency=max_concurrency
                )
                
                self.service.save_files(chunk_results, aggregated_result, out_path, lecture_id)
                
                chunk_file = out_path / f"{lecture_id}_chunks.json"
                aggregated_file = out_path / f"{lecture_id}_summary.json"

                file_elapsed = time.perf_counter() - file_start_time
                print(f"완료: {lecture_id} | 청크 {len(chunk_results)}개 처리 | 소요 시간: {file_elapsed:.2f}초")
                
                results[lecture_id] = {
                    "chunk_results": chunk_results,
                    "aggregated_result": aggregated_result,
                    "chunk_file": str(chunk_file),
                    "aggregated_file": str(aggregated_file),
                }
                
            except Exception as exc:
                file_elapsed = time.perf_counter() - file_start_time
                error_type = type(exc).__name__
                error_msg = str(exc)

                if hasattr(exc, "__cause__") and exc.__cause__:
                    cause = exc.__cause__
                    error_msg = f"{error_msg} (caused by: {type(cause).__name__}: {str(cause)[:200]})"

                errors[lecture_id] = f"{error_type}: {error_msg}"

                if continue_on_error:
                    print(f"오류 ({file_elapsed:.2f}초): {lecture_id} - {error_type}: {error_msg[:150]}")
                    if len(error_msg) > 150:
                        print(f"   ... (생략)")
                    print(f"   다음 파일로 계속 진행합니다...")
                else:
                    raise RuntimeError(
                        f"처리 실패 {lecture_id}: {error_type}: {error_msg}"
                    ) from exc

        batch_elapsed = time.perf_counter() - batch_start_time
        total = len(transcript_files)
        print(f"\n[배치 처리 요약] 총 {total}건 중 {len(results)}건 성공, {len(errors)}건 실패")
        print(f"총 소요 시간: {batch_elapsed:.2f}초 (평균 {batch_elapsed / total:.2f}초/건)" if total else "총 소요 시간: 0.00초")

        if errors:
            print(f"\n{len(errors)}개 파일 처리 실패:")
            for lecture_id, error_msg in errors.items():
                print(f"   - {lecture_id}: {error_msg}")
        
        return results

    def _resolve_directory(self, target_dir: str | Path) -> Path:
        directory = Path(target_dir).resolve()
        if directory.exists():
            return directory

        current = Path.cwd()
        while current != current.parent:
            candidate = current / target_dir
            if candidate.exists():
                return candidate.resolve()
            current = current.parent
            
        return directory

    def process_directory(
        self,
        transcript_dir: str | Path,
        output_dir: str | Path,
        pattern: str = "*.txt",
        continue_on_error: bool = True,
        max_concurrency: int = 1,
        latest_only: bool = False,
    ) -> Dict[str, dict]:
        directory = self._resolve_directory(transcript_dir)
        
        if not directory.exists():
            raise FileNotFoundError(f"스크립트 폴더를 찾을 수 없습니다: {directory}")

        files = sorted(directory.glob(pattern))
        if not files:
            raise FileNotFoundError(f"'{pattern}' 패턴에 맞는 스크립트 파일이 없습니다: {directory}")

        if latest_only:
            latest_file = max(files, key=lambda f: f.stat().st_mtime)
            print(f"최신 문서 모드: {latest_file.name} 1건만 분석합니다.")
            files = [latest_file]

        return self.process_files(
            transcript_files=files,
            output_dir=output_dir,
            continue_on_error=continue_on_error,
            max_concurrency=max_concurrency,
        )

if __name__ == "__main__":
    import argparse
    from src.llm_engine.infrastructure.llm.openai_adapter import OpenAIAdapter
    from src.llm_engine.infrastructure.persistence.json_repo import LocalJsonRepository
    
    parser = argparse.ArgumentParser(description="강의 스크립트 배치 처리기")
    parser.add_argument("--input", "-i", type=str, default="data/raw", help="스크립트 폴더 경로")
    parser.add_argument("--output", "-o", type=str, default="data/outputs/llm", help="결과 저장 폴더 경로")
    parser.add_argument("--max_concurrency", "-c", type=int, default=3, help="동시 처리 청크 수")
    parser.add_argument("--file", "-f", type=str, help="특정 파일 하나만 처리할 경우 해당 파일의 경로 입력")
    parser.add_argument("--latest", "-l", action="store_true", help="지정된 폴더에서 가장 최신 스크립트 1개만 처리")
    
    args = parser.parse_args()

    llm_provider = OpenAIAdapter()
    repository = LocalJsonRepository()
    service = LectureAnalyzerService(llm_provider, repository)
    processor = BatchProcessor(service)

    try:
        if args.file:
            file_path = Path(args.file).resolve()
            if not file_path.exists():
                raise FileNotFoundError(f"지정된 파일을 찾을 수 없습니다: {file_path}")
            print(f"단일 파일 지정: {file_path.name}")
            processor.process_files([file_path], args.output, max_concurrency=args.max_concurrency)
        else:
            processor.process_directory(
                transcript_dir=args.input, 
                output_dir=args.output, 
                max_concurrency=args.max_concurrency,
                latest_only=args.latest
            )
    except Exception as e:
        print(f"\n실행 오류: {e}")

