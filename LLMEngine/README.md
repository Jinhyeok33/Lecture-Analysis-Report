# LLMEngine

강의 스크립트를 청크 단위로 분석하고 결과를 JSON으로 저장하는 배치 처리기입니다.

## 사전 준비

1. **의존성 설치**
   이 저장소를 클론한 폴더 루트에서 아래 명령어를 실행하세요.
   ```bash
   pip install -r requirements.txt
   ```

2. **API 키 설정**
   저장소 루트에 `.env` 파일을 만들고 다음 내용을 넣어주세요.
   ```env
   OPENAI_API_KEY=sk-your-key-here
   ```

## 실행 방법

작업 디렉터리는 반드시 이 저장소를 클론한 폴더(루트)로 맞춘 뒤 실행해야 합니다.
(루트에 `LLMEngine/`, `docs/`, `dataset/` 등이 보이는 위치)
> ex. `ik/LLMEngine`, `ik/docs`, `ik/dataset` 등의 형태

### Windows (PowerShell)
```powershell
cd path\to\클론한_저장소
$env:PYTHONPATH = "."
python -m LLMEngine.entrypoints.batch_processor
```

### Windows (CMD)
```cmd
cd path\to\클론한_저장소
set PYTHONPATH=.
python -m LLMEngine.entrypoints.batch_processor
```

### Linux / Mac
```bash
cd path/to/클론한_저장소
export PYTHONPATH=.
python -m LLMEngine.entrypoints.batch_processor
```

## CLI 옵션

| 옵션 | 약어 | 기본값 | 설명 |
|------|------|--------|------|
| `--input` | `-i` | `dataset/강의 스크립트` | 스크립트가 들어 있는 폴더 |
| `--output` | `-o` | `./output` | 결과 JSON을 저장할 폴더 |
| `--max_concurrency` | `-c` | `3` | 동시에 처리할 청크 수 (윈도우는 1 권장) |
| `--file` | `-f` | - | 지정한 스크립트 파일 하나만 처리 |
| `--latest` | `-l` | - | 입력 폴더에서 가장 최신 파일 1개만 처리 |

## 실행 예시

```bash
# 기본: dataset/강의 스크립트 안의 파일 전체 처리
python -m LLMEngine.entrypoints.batch_processor

# 입력·출력 폴더 직접 지정
python -m LLMEngine.entrypoints.batch_processor -i "dataset/강의 스크립트" -o "LLMEngine/output"

# 단일 파일만 처리
python -m LLMEngine.entrypoints.batch_processor -f "dataset/강의 스크립트/2026-03-02_xxx.txt" -o "./output"

# 방금 올린 최신 파일 1개만 빠르게 처리
python -m LLMEngine.entrypoints.batch_processor -l -o "./output"
```

## 결과 파일

실행이 완료되면 `--output`으로 지정한 폴더에 다음 두 종류의 파일이 생성됩니다.

- `{lecture_id}_chunks.json` : 청크별 분석 상세 결과
- `{lecture_id}_summary.json` : 통합 요약 결과