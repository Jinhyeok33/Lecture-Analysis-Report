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
   **Gemini 사용 시:** `GEMINI_API_KEY=...` 를 넣습니다. `OPENAI_API_KEY`가 없으면 **자동으로 Gemini**를 씁니다. 둘 다 있으면 기본은 OpenAI이며, **`LLM_BACKEND=gemini`** 로 고를 수 있습니다.  
   무료 티어는 **분당 요청·토큰 한도**가 작습니다. 동시 청크는 **`python -m LLMEngine.entrypoints.batch_processor -c 1`** 을 권장합니다. `429 RESOURCE_EXHAUSTED`·`free_tier_*` 가 보이면 [Gemini API 할당량](https://ai.google.dev/gemini-api/docs/rate-limits)을 확인하거나 결제(유료 할당)를 켠 뒤 재시도하세요.

## 실행 방법

작업 디렉터리는 반드시 이 저장소를 클론한 폴더(루트)로 맞춘 뒤 실행해야 합니다.
(루트에 `LLMEngine/`, `docs/`, `dataset/` 등이 보이는 위치)
> ex. `ik/LLMEngine`, `ik/docs`, `ik/dataset` 등의 형태

### Windows (PowerShell)
```powershell
cd path\to\클론한_저장소
python -m LLMEngine.entrypoints.batch_processor
```

### Windows (CMD)
```cmd
cd path\to\클론한_저장소
python -m LLMEngine.entrypoints.batch_processor
```

### Linux / Mac (Git Bash 포함)
```bash
cd path/to/클론한_저장소
python -m LLMEngine.entrypoints.batch_processor
```

> **PYTHONPATH 설정 불필요**  
> `python -m` 실행 시 Python이 현재 디렉터리(`ik/`)를 자동으로 sys.path에 추가합니다.  
> 코드 내 모든 임포트가 `from LLMEngine.xxx import` 형식이므로 별도 설정 없이 동작합니다.

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
- `{lecture_id}_summary.json` : 통합 요약 결과 + 운영 메타데이터

### run_metadata (summary.json 포함 필드)

`_summary.json`의 `run_metadata`에는 강의 1건 처리 단위의 운영 메타데이터가 포함됩니다.

| 필드 | 설명 |
|------|------|
| `schema_version` | 출력 스키마 버전. 하위 호환 불가 변경 시 올린다. |
| `checkpoint_version` | 체크포인트 파일 포맷 버전 |
| `prompt_version` | 사용된 프롬프트 버전 (품질 회귀 추적용) |
| `model` | 사용된 LLM 모델명 |
| `total_chunks` | 전체 청크 수 |
| `scored_chunks` | 실제 점수 집계에 사용된 청크 수 (fallback 제외) |
| `successful_chunks` | 분석 성공 청크 수 |
| `fallback_chunks` | fallback 기본값 청크 수 |
| `refused_chunks` | 모델 refusal 청크 수 |
| `failed_chunks` | 기타 실패 청크 수 |
| `evidence_count_total` | 전체 evidence 항목 수 |
| `token_usage` | `prompt_tokens`, `completion_tokens`, `total_tokens`, `estimated_cost_usd`, `llm_call_count` |

`scored_chunks < total_chunks`이면 일부 청크가 fallback/실패 상태였음을 의미합니다.
점수 신뢰도를 판단할 때 반드시 확인하세요.

### 청크 분할 기본값

| 설정 | 기본값 |
|------|--------|
| 청크 길이 | **12분** |
| 오버랩 | **2분** |

청크 길이를 바꾸려면 `core/config.py`의 `chunk_duration_minutes`를 수정하세요.

---

## 입력 포맷 계약

`dataset/강의 스크립트/` 에 놓이는 STT 파일은 다음 포맷을 **반드시** 따라야 합니다.

```
<HH:MM:SS> 화자명: 발화 텍스트
```

예시:
```
<00:00:05> 강사: 안녕하세요, 오늘은 백엔드 기초를 다룹니다.
<00:00:12> 강사: 먼저 HTTP 프로토콜부터 시작할게요.
<00:01:04> 학생1: 질문 있습니다. REST와 HTTP 차이가 뭔가요?
```

**포맷 불일치 시 동작:**

| `strict_parse` | 동작 |
|---|---|
| `False` (기본) | 불일치 라인을 직전 라인에 병합 + `WARNING` 로그 출력 |
| `True` | 즉시 `ValueError` 발생으로 파이프라인 중단 |

`parse_failure_count > 0`인 경우 `WARNING` 로그에 불일치 라인 수가 출력됩니다.
upstream에서 STT 포맷을 변경할 경우 반드시 LLMEngine 팀에 사전 공지해야 합니다.

---

## lecture_id / run 번호 규칙

### 형식

```
{날짜}_{강의코드}_{기타식별자}_NN
```

- `NN`: 항상 **두 자리** zero-padding (`_01`, `_02`, ...)
- 같은 스크립트를 재실행하면 run 번호가 1씩 증가한다.
- 체크포인트 파일명(`checkpoint/{lecture_id}.json`), 출력 파일명(`{lecture_id}_chunks.json` / `{lecture_id}_summary.json`) 모두 이 규칙을 따른다.

### 재실행(이어 받기) 정책

동일한 `lecture_id`로 재실행하면 기존 체크포인트를 불러와 완료된 청크를 건너뜁니다.  
**체크포인트 손상 시** `json.JSONDecodeError`가 발생하며 파이프라인이 중단됩니다.  
복구 방법:
1. 손상된 `checkpoint/{lecture_id}.json`을 삭제한다.
2. 재실행하면 처음부터 다시 처리한다.

체크포인트 포맷이 변경될 경우 `schemas.py`의 `CHECKPOINT_VERSION`을 올리고,
이전 버전 체크포인트는 삭제 후 재실행해야 합니다.

---

## 비용 확인

배치 실행 완료 후 로그의 `stage=batch_done` 라인에서 비용을 확인합니다.

```
stage=batch_done total=3 success=3 failed=0 elapsed_ms=12345 total_tokens=42000 estimated_cost_usd=0.063000
```

강의 1건 단위 비용은 `{lecture_id}_summary.json`의 `run_metadata.token_usage.estimated_cost_usd`에서 확인합니다.

> **주의**: `estimated_cost_usd`는 모델 공시 단가 기준 추정값입니다. 실제 청구 금액은 OpenAI 콘솔에서 확인하세요.

---

## PII / 민감정보 처리 정책

LLMEngine은 STT 원문을 **그대로** OpenAI API에 전송합니다.  
강의 스크립트에 수강생 이름·연락처·개인 식별 정보가 포함될 경우, **LLMEngine 입력 전** upstream(STT 처리 단계)에서 마스킹·비식별화 처리를 완료해야 합니다.

- LLMEngine 내부에는 PII 마스킹 로직이 없습니다.
- 비식별화 책임은 STT 원문을 생성·제공하는 upstream 팀에 있습니다.
- 운영 환경에서 개인정보 처리 방침을 변경하는 경우 이 문서를 함께 갱신하세요.

---

## 프롬프트 버전 관리

`application/prompts.py`의 `PROMPT_VERSION` 상수로 프롬프트 버전을 관리합니다.  
분석 결과의 `run_metadata.prompt_version`에 사용된 버전이 기록됩니다.

**버전 올리는 기준:**

| 변경 종류 | 조치 |
|---|---|
| 평가 기준·점수 척도 변경 | `PROMPT_VERSION` 올리기 (예: `v2.0` → `v2.1`) |
| 지시문 추가·삭제 | `PROMPT_VERSION` 올리기 |
| 오탈자·표현 수정 | 올리지 않아도 됨 (재현성에 영향 없음) |

**회귀 추적:**  
프롬프트를 변경한 경우 동일 스크립트로 이전 버전과 결과를 비교해 점수 분포가 크게 달라지는지 확인하세요.  
`run_metadata.prompt_version`이 다른 두 결과를 직접 비교하는 것은 의미가 없습니다.