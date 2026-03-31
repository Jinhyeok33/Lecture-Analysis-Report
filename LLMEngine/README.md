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
| `--max_concurrency` | `-c` | `1` | 동시에 처리할 청크 수 |
| `--file` | `-f` | - | 지정한 스크립트 파일 하나만 처리 |
| `--latest` | `-l` | - | 입력 폴더에서 가장 최신 파일 1개만 처리 |
| `--repo` | - | `json` | 체크포인트 저장소 (`json`: 파일, `sqlite`: DB) |

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

# SQLite 체크포인트 저장소 사용
python -m LLMEngine.entrypoints.batch_processor --repo sqlite -o "./output"
```

---

## 테스트 러너 (test_runner)

JSONL 기반 자동 테스트를 실행해 프롬프트·엔진 변경의 품질 회귀를 확인합니다.  
각 테스트 케이스를 **단일 청크**로 변환해 LLM에 보내고, 기대 점수 범위 내에 있는지 PASS/FAIL을 판정합니다.

### 기본 실행

```bash
python -m LLMEngine.entrypoints.test_runner
```

기본 테스트 파일: `docs/test_cases_llm.jsonl`  
결과는 `testcase_result/testcase_YYMMDD_HHMMSS.json` (KST 기준)에 자동 저장됩니다.

### CLI 옵션

| 옵션 | 약어 | 기본값 | 설명 |
|------|------|--------|------|
| `--jsonl` | `-j` | `docs/test_cases_llm.jsonl` | 테스트 케이스 JSONL 파일 경로 |
| `--item` | `-i` | 전체 | 실행할 item_id 목록 (공백 구분) |
| `--category` | `-c` | 전체 | 실행할 category 목록 (공백 구분) |
| `--stop-on-fail` | - | `false` | 첫 번째 실패 시 이후 케이스 중단 |
| `--verbose` | `-v` | `false` | 실패 이유를 즉시 상세 출력 |
| `--model` | - | config 기본값 | 사용할 LLM 모델명 |
| `--temperature` | - | config 기본값 (0.5) | LLM temperature |
| `--seed` | - | config 기본값 (42) | 재현성용 seed (OpenAI 전용) |
| `--output` | `-o` | 자동 생성 | 결과 JSON 저장 경로 직접 지정 |

### 실행 예시

```bash
# 전체 테스트 + 상세 출력
python -m LLMEngine.entrypoints.test_runner --verbose

# 특정 항목만 테스트
python -m LLMEngine.entrypoints.test_runner --item learning_objective_intro closing_summary

# 특정 카테고리만 테스트
python -m LLMEngine.entrypoints.test_runner --category lecture_structure interaction

# 첫 실패 시 중단 + 상세
python -m LLMEngine.entrypoints.test_runner --stop-on-fail -v

# 결과 파일 경로 직접 지정
python -m LLMEngine.entrypoints.test_runner -o result.json
```

### 결과 파일 형식

`testcase_result/testcase_YYMMDD_HHMMSS.json`:

```json
{
  "run_timestamp_kst": "2026-03-27T12:24:02+09:00",
  "prompt_version": "v4.3",
  "total": 54,
  "passed": 43,
  "failed": 11,
  "results": [
    {
      "test_id": "TC-LS-001",
      "title": "학습 목표 명확히 제시",
      "item_id": "learning_objective_intro",
      "category": "lecture_structure",
      "test_type": "positive",
      "expected_range": [4, 5],
      "actual_score": 5,
      "passed": true,
      "chunk_status": "SUCCESS",
      "elapsed_ms": 3200,
      "failure_reason": null,
      "notes": ""
    }
  ]
}
```

> **종료 코드**: 실패 케이스가 1건이라도 있으면 `exit code 1`, 전체 통과 시 `exit code 0`.

> **주의**: `test_runner`는 현재 **OpenAI 어댑터만 지원**합니다.  
> `batch_processor`처럼 `LLM_BACKEND=gemini` 자동 전환이 되지 않으므로, Gemini로 테스트하려면 코드 수정이 필요합니다.

---

## 체크포인트 뷰어 (checkpoint_viewer)

체크포인트 파일에서 **LLM 호출 없이** 분석 진행 상황을 확인하고, 미완료 체크포인트를 output JSON으로 내보낼 수 있습니다.

### 기본 실행

```bash
# 미완료 체크포인트 자동 탐색
python -m LLMEngine.entrypoints.checkpoint_viewer

# 모든 체크포인트 요약
python -m LLMEngine.entrypoints.checkpoint_viewer --all

# 특정 체크포인트 파일 확인
python -m LLMEngine.entrypoints.checkpoint_viewer -c checkpoints/260205_03_checkpoint.json

# 상세 출력 (청크별 상태 + evidence 샘플)
python -m LLMEngine.entrypoints.checkpoint_viewer --all -v

# 미완료 체크포인트 → output JSON 내보내기 (LLM 호출 없음)
python -m LLMEngine.entrypoints.checkpoint_viewer --export

# SQLite 저장소에서 특정 lecture_id 조회
python -m LLMEngine.entrypoints.checkpoint_viewer --repo sqlite --lecture-id 260302_kdt_01
```

### CLI 옵션

| 옵션 | 약어 | 기본값 | 설명 |
|------|------|--------|------|
| `--checkpoint` | `-c` | - | 특정 체크포인트 파일 경로 |
| `--all` | `-a` | `false` | 모든 체크포인트 요약 출력 |
| `--verbose` | `-v` | `false` | 청크별 상태 + evidence 샘플 포함 |
| `--export` | `-e` | `false` | 미완료 체크포인트를 output JSON으로 내보내기 |
| `--repo` | - | `json` | 저장소 유형 (`json`: 파일, `sqlite`: DB) |
| `--checkpoint-dir` | - | `./checkpoints` | 체크포인트 디렉토리 |
| `--output-dir` | - | `./output` | 내보내기 출력 디렉토리 |
| `--lecture-id` | - | - | SQLite 사용 시 특정 lecture_id 조회 |

### `--export` 동작

`--export`는 체크포인트에 저장된 성공 청크 결과를 기반으로 `{lecture_id}_chunks.json`과 `{lecture_id}_summary.json`을 생성합니다.
LLM을 재호출하지 않으므로, 강점/이슈 요약은 청크별 원본이 그대로 수집됩니다 (LLM 통합 요약 없음).

---

## JSON Schema 계약서 내보내기 (export_schema)

Pydantic 모델에서 JSON Schema를 자동 추출하여 `contracts/` 디렉토리에 저장합니다.

```bash
python -m LLMEngine.entrypoints.export_schema
```

생성되는 파일:
- `contracts/ChunkResult_Schema.json` — 청크별 분석 결과 스키마
- `contracts/AggregatedResult_Schema.json` — 통합 요약 결과 스키마

다운스트림 시스템과의 인터페이스 계약으로 활용하거나, 스키마 변경 시 차이를 추적하는 데 사용합니다.

---

## 환경 변수 설정

`.env` 파일 또는 시스템 환경 변수로 엔진 동작을 조정할 수 있습니다.

| 환경 변수 | 기본값 | 설명 |
|-----------|--------|------|
| `OPENAI_API_KEY` | - | OpenAI API 키 (필수) |
| `GEMINI_API_KEY` | - | Gemini API 키 (OpenAI 없을 시 자동 전환) |
| `LLM_BACKEND` | `openai` | `gemini` 로 설정하면 Gemini 강제 사용 |
| `LLM_MODEL` | `gpt-4o-2024-08-06` | 분석용 LLM 모델명 (OpenAI 사용 시) |
| `GEMINI_MODEL` | `gemini-2.0-flash` | 분석용 Gemini 모델명 |
| `GEMINI_DEDUP_MODEL` | `gemini-2.0-flash` | 통합 요약용 Gemini 모델명 |
| `LLM_MAX_RETRIES` | `5` | 청크 분석 최대 재시도 횟수 |
| `LLM_RETRY_BASE_DELAY` | `2.0` | 재시도 기본 대기 시간 (초, exponential backoff) |
| `LLM_CHUNK_DURATION_MINUTES` | `12` | 청크 분할 길이 (분) |
| `LLM_OVERLAP_MINUTES` | `2` | 청크 오버랩 (분) |
| `LLM_API_TIMEOUT_S` | `120.0` | API 호출 타임아웃 (초) |
| `LLM_MAX_CONCURRENCY` | `1` | 동시 청크 처리 수 |
| `LLM_MAX_COMPLETION_TOKENS` | `2500` | 응답 최대 토큰 |
| `LLM_TEMPERATURE` | `0.5` | LLM temperature |
| `LLM_SEED` | `42` | 재현성용 seed (OpenAI 전용, Gemini는 무시) |
| `LLM_LOG_FORMAT` | `text` | `json` 으로 설정하면 구조화 JSON 로깅 활성화 |
| `LLM_LOG_LEVEL` | `INFO` | 로그 레벨 (DEBUG, INFO, WARNING, ERROR) |
| `LLM_PROMPT_VERSION` | `v4.3` | 사용할 프롬프트 버전 (YAML 외부 파일 연동) |

### 이중 모델 전략 (분석 vs 통합 요약)

LLMEngine은 **청크 분석**과 **통합 요약**에 서로 다른 모델을 사용합니다.
청크 분석에는 고성능 모델을, 통합 요약(강점/이슈 중복 제거)에는 경량 모델을 사용하여 비용을 절감합니다.

| 용도 | OpenAI 기본 | Gemini 기본 |
|------|-------------|-------------|
| 청크 분석 (Fact Collector) | `gpt-4o-2024-08-06` | `gemini-2.0-flash` |
| 통합 요약 (Report Synthesizer) | `gpt-4o-mini` | `gemini-2.0-flash` |

---

## 결과 파일

실행이 완료되면 `--output`으로 지정한 폴더에 다음 두 종류의 파일이 생성됩니다.

- `{lecture_id}_chunks.json` : 청크별 분석 상세 결과
- `{lecture_id}_summary.json` : 통합 요약 결과 + 운영 메타데이터

### chunks.json 청크별 필드

각 청크 객체에는 다음 필드가 포함됩니다.

| 필드 | 설명 |
|------|------|
| `chunk_id` | 청크 번호 (1부터 시작) |
| `start_time` / `end_time` | 강의 내 시간 구간 (HH:MM) |
| `scores` | 4개 카테고리 × 13개 항목 점수 (1~5, N/A는 null) |
| `strengths` / `issues` | 강점·문제점 리스트 |
| `evidence` | 근거 리스트 (`item`, `quote`, `reason`) |
| `status` | `SUCCESS`, `FAILED`, `REFUSED`, `TIMED_OUT`, `CANCELLED` |
| `is_fallback` | fallback 기본값 사용 여부 |
| `retry_count` | 재시도 횟수 |
| `elapsed_ms` | 해당 청크 분석 소요 시간 (밀리초, 재시도 포함) |
| `token_usage` | 토큰 수, 비용, API 호출 횟수 |
| `reliability` | 청크별 신뢰도 지표 (evidence pass ratio, 유사도 등) |

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
| `total_elapsed_ms` | 강의 1건 전체 처리 소요 시간 (밀리초) |
| `token_usage` | `prompt_tokens`, `completion_tokens`, `total_tokens`, `estimated_cost_usd`, `llm_call_count` |
| `reliability` | 분석 결과 신뢰도 지표 (아래 상세) |

`scored_chunks < total_chunks`이면 일부 청크가 fallback/실패 상태였음을 의미합니다.
점수 신뢰도를 판단할 때 반드시 확인하세요.

### reliability (신뢰도 지표)

`run_metadata.reliability`에는 분석 결과 자체의 신뢰도를 정량화한 지표가 포함됩니다.

| 필드 | 범위 | 설명 |
|------|------|------|
| `evidence_pass_ratio` | 0.0~1.0 | evidence 원문 매칭 통과 비율 |
| `hallucination_retries` | 0~ | 환각 감지로 인한 재시도 총 횟수 |
| `avg_evidence_similarity` | 0.0~100.0 | 통과 evidence의 평균 유사도 (0-100) |
| `score_evidence_consistency` | 0.0~1.0 | 비기본(≠3) 점수 항목 중 evidence 보유 비율 |
| `overall_reliability_score` | 0.0~1.0 | 종합 신뢰도 (가중 합산, 아래 공식) |

**`overall_reliability_score` 산출 공식:**

```
overall = 0.35 × evidence_pass_ratio
        + 0.25 × (1.0 - min(hallucination_retries / 3.0, 1.0))
        + 0.20 × (avg_evidence_similarity / 100.0)
        + 0.20 × score_evidence_consistency
```

`overall_reliability_score`가 0.7 미만이면 분석 결과를 수동 검토하는 것을 권장합니다.

### 엔진 정확도 (프롬프트 v4.3 기준)

#### 테스트케이스 기반 정확도

54개 테스트케이스(`docs/test_cases_llm.jsonl`)에 대한 `test_runner` 실행 결과:

| 실행 | 프롬프트 | 통과 | 통과율 |
|------|---------|------|--------|
| 2026-03-27 10:32 | v4.3 | 43/54 | **79.6%** |
| 2026-03-27 11:36 | v4.3 | 38/54 | 70.4% |

동일 프롬프트에서도 LLM 응답의 비결정성으로 **70~80% 범위**에서 편차가 발생합니다.

**주요 실패 패턴 (v4.3 최고 결과 43/54 기준):**

| 유형 | 건수 | 패턴 |
|------|:---:|------|
| borderline 과소 평가 (실제 < 기대 하한) | 5 | `closing_summary`, `concept_definition`, `prerequisite_check`, `practice_transition` 등 경계 케이스에서 1점 낮게 채점 |
| positive 과소 평가 | 3 | `previous_lesson_linkage`, `closing_summary`, `question_response_sufficiency`에서 기대 4~5점 대비 2~3점 |
| borderline 과대 평가 (실제 > 기대 상한) | 2 | `error_handling`, `practice_transition`에서 기대 2.8~3.8 대비 4점 |
| negative 과대 평가 | 1 | `example_appropriateness`에서 기대 1~2점 대비 3점 |

> borderline 테스트(기대 범위 폭 ~1.0)의 ±1점 편차가 전체 실패의 대부분을 차지합니다.
> positive/negative 극단 케이스는 높은 적중률을 보입니다.

#### 실제 강의 분석 정확도 (batch_processor)

동일 강의(`2026-02-27`)를 2회 실행한 결과:

| 지표 | 1차 (run 02) | 2차 (run 03) |
|------|:---:|:---:|
| 성공률 | 34/34 (100%) | 34/34 (100%) |
| evidence pass ratio | 97.1% | **100%** |
| 평균 evidence 유사도 | 97.0% | **99.95%** |
| 점수-근거 일관성 | 68.6% | **70.4%** |
| 전체 신뢰도 | 0.9208 | **0.9407** |
| 환각 재시도 | 0회 | 0회 |

두 실행 간 항목별 평균 점수 편차는 ±0.2 이내로, **채점 일관성이 높은 수준**입니다.

#### 정확도 요약

| 측면 | 수치 | 평가 |
|------|------|------|
| 테스트케이스 통과율 | 70~80% | borderline ±1점 편차 포함, 극단 케이스 적중률 높음 |
| 실행 간 재현성 | 점수 편차 ±0.2 | LLM 비결정성 대비 안정적 |
| evidence 신뢰도 | 97~100% | 인용 근거가 원문에 실재하는 비율 |
| 환각 발생률 | 0% | CoT 구조화 + evidence 검증으로 억제 |

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

**해시 화자명 자동 처리:**  
화자명이 hex hash(예: `a1b2c3d4`)인 경우, 청크 텍스트에서 `화자명:` 접두사를 자동 제거하고 발화 텍스트만 포함합니다.
일반 화자명(`강사`, `학생1` 등)은 `강사: 발화 텍스트` 형식으로 유지됩니다.

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

## Evidence 검증 (환각 탐지)

LLM이 생성한 evidence의 `quote`가 실제 청크 원문에 존재하는지 유사도 기반으로 검증합니다.
검증에 실패하면 `HallucinationError`가 발생하여 해당 청크를 재시도합니다.

| 상수 | 값 | 설명 |
|------|-----|------|
| `DEFAULT_SIMILARITY_THRESHOLD` | `0.80` | quote↔원문 유사도 통과 기준 (0-1) |
| `HALLUCINATION_MIN_PASS_RATIO` | `0.50` | evidence 중 최소 통과 비율. 미달 시 환각 판정 |
| `HALLUCINATION_MAX_EFFECTIVE_REQUEST` | `6` | 통과율 산정 시 분모 상한 (evidence가 많을 때 과도한 실패 방지) |
| `PREVIOUS_CHUNK_TAIL_MAX_CHARS` | `1500` | 이전 청크 꼬리 문맥의 최대 문자 수 |

유사도 측정에는 `rapidfuzz` 라이브러리를 사용합니다. 미설치 시 `difflib.SequenceMatcher`로 자동 fallback합니다.

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

---

## 단위 테스트

LLM API 호출 없이 mock/fake 객체로 전체 파이프라인을 검증합니다.

```bash
# 전체 테스트 실행
python -m pytest LLMEngine/tests/ -v

# 특정 모듈만
python -m pytest LLMEngine/tests/test_schemas.py -v

# 커버리지 포함
python -m pytest LLMEngine/tests/ --cov=LLMEngine --cov-report=term-missing
```

### 테스트 구성 (242개)

| 파일 | 검증 대상 | 테스트 수 |
|------|-----------|-----------|
| `test_schemas.py` | Pydantic 모델, 점수 범위, 정규화, 시간 검증 | 17 |
| `test_chunk_processor.py` | 스크립트 파싱, 청크 분할, 경계 케이스 | 10 |
| `test_validation.py` | evidence 유사도, 환각 탐지, 빈 리스트 | 11 |
| `test_aggregator.py` | 점수 집계, 신뢰도, fallback 처리 | 9 |
| `test_analyzer_service.py` | 파이프라인 통합, NA 정책, 체크포인트, 파일 저장 | 14 |
| `test_config.py` | 환경 변수 파싱, 기본값, nested config, **immutability** | 22 |
| `test_prompts.py` | 프롬프트 생성, 위치 힌트, 이전 청크 주입 | 8 |
| `test_json_repo.py` | JSON 저장소 CRUD, 손상 복구, atomic write | 8 |
| `test_sqlite_repo.py` | SQLite 저장소 CRUD, 영속성, 서비스 통합 | 8 |
| `test_schema_sync.py` | VALID_ITEMS↔Scores 동기화, 카테고리 정합성 | 6 |
| `test_logging_config.py` | JSON/텍스트 포맷터, 중복 초기화, **trace_id** | 13 |
| `test_base_adapter.py` | 재시도 루프, 검증 체인, 비용 계산, 중복 제거 | 25 |
| `test_concurrency.py` | 비동기 배치, fallback executor, 경계값 | 11 |
| `test_prompt_registry.py` | YAML 로딩, fallback, 캐시, 버전 목록 | 7 |
| `test_metrics.py` | 카운터, 히스토그램, 타이머, 태그 | 7 |
| `test_ab_testing.py` | A/B 비교, 점수 차이, 일치율 | 5 |
| `test_secrets.py` | 시크릿 프로바이더, 체인, 필수 키 검증 | 9 |
| `test_sdk_parsing.py` | **OpenAI/Gemini SDK 응답 mock 파싱, 에러 경로** | 16 |
| `test_integration.py` | **end-to-end 파이프라인, context manager, 멀티파일** | 8 |

---

## 구조화 로깅

`LLM_LOG_FORMAT=json` 환경 변수로 JSON 구조화 로깅을 활성화할 수 있습니다.

```bash
# JSON 포맷 로깅
LLM_LOG_FORMAT=json python -m LLMEngine.entrypoints.batch_processor
```

JSON 로그 출력 예시:
```json
{"ts": "2026-03-27T15:30:00.123+09:00", "level": "INFO", "logger": "LLMEngine.entrypoints.batch_processor", "trace_id": "a1b2c3d4e5f6", "msg": "stage=start file=2026-03-02_kdt.txt lecture_id=260302_kdt_01"}
```

개발 환경에서는 기본값(`text`)으로 사람 친화적 포맷이 출력됩니다:
```
15:30:00 [INFO ] LLMEngine.entrypoints.batch_processor — [a1b2c3d4e5f6] stage=start file=2026-03-02_kdt.txt
```

### trace_id (요청 추적)

`batch_processor`는 강의 파일 처리 시작 시 자동으로 `trace_id`를 생성합니다.
모든 로그에 `trace_id`가 포함되어 특정 강의 처리 과정을 추적할 수 있습니다.

```python
from LLMEngine.core.logging_config import set_trace_id, get_trace_id

set_trace_id("custom-id")  # 수동 설정
set_trace_id()              # UUID 자동 생성
```

---

## 저장소 전환 (JSON → SQLite)

`--repo sqlite` 옵션으로 SQLite 체크포인트 저장소를 사용할 수 있습니다.

```bash
python -m LLMEngine.entrypoints.batch_processor --repo sqlite
```

| 저장소 | 파일 | 동시 접근 | 규모 한계 |
|--------|------|-----------|-----------|
| `json` (기본) | `checkpoints/{lecture_id}_checkpoint.json` | 단일 프로세스 | 소규모 |
| `sqlite` | `checkpoints.db` | WAL 모드 멀티 프로세스 | 대규모 |

두 저장소 모두 `IRepository` 인터페이스를 구현하므로, 코드 변경 없이 DI로 전환할 수 있습니다.

---

## 프롬프트 외부 파일 관리 (YAML)

프롬프트를 YAML 파일로 외부화하여 코드 배포 없이 A/B 테스트가 가능합니다.

```bash
# 프롬프트 디렉토리: LLMEngine/prompts/
# v4.3.yaml 파일을 생성하면 코드 내장 프롬프트 대신 사용
LLM_PROMPT_VERSION=v4.4 python -m LLMEngine.entrypoints.batch_processor
```

YAML 파일이 없으면 `prompts.py`의 내장 프롬프트로 자동 fallback됩니다.
상세 가이드는 `LLMEngine/prompts/README.md`를 참조하세요.

> **의존성**: YAML 프롬프트 로딩에는 `pyyaml` 패키지가 필요합니다.
> ```bash
> pip install pyyaml
> ```
> `pyyaml` 미설치 시 YAML 로딩을 건너뛰고 코드 내장 프롬프트를 사용합니다.

---

## 설정 구조 (nested config)

`LLMEngineConfig`는 세 하위 config로 구성됩니다:

| 클래스 | 담당 | 주요 필드 |
|--------|------|-----------|
| `ChunkConfig` | 청크 분할 | `duration_minutes`, `overlap_minutes` |
| `LLMConfig` | LLM 호출 | `model`, `temperature`, `seed`, `max_completion_tokens` |
| `NetworkConfig` | 네트워크 | `max_retries`, `retry_base_delay`, `api_timeout_s`, `max_concurrency` |

모든 config 클래스는 `frozen=True`로 불변(immutable)이며, 생성 후 변경이 불가합니다.
기존 flat 속성(`config.temperature`, `config.max_retries` 등)은 프로퍼티로 유지되어 하위 호환됩니다.

---

## 메트릭 수집 (Observability)

`core/metrics.py`의 `MetricsCollector`로 LLM 호출 시간, 비용, 재시도 횟수를 인메모리 수집합니다.

```python
from LLMEngine.core.metrics import get_metrics

metrics = get_metrics()
print(metrics.summary())
# {'counters': {'llm_call_total': 15.0}, 'histograms': {'llm_call_duration_s': {...}}}
```

Prometheus/OpenTelemetry 연동 시 `MetricsCollector`를 상속하여 `flush()`를 오버라이드합니다.

---

## 멀티 모델 A/B 테스트

`core/ab_testing.py`의 `ABTestRunner`로 동일 스크립트를 여러 모델로 비교합니다.

```python
from LLMEngine.core.ab_testing import ABTestRunner

runner = ABTestRunner([openai_adapter, gemini_adapter])
results = runner.run_comparison(chunks)
comparisons = runner.compare_scores(results)
runner.save_comparison(results, comparisons, "ab_result.json")
```

---

## API 키 관리 (시크릿 매니저)

기본은 환경 변수에서 키를 읽지만, `core/secrets.py`의 `SecretProvider`를 확장하여
AWS SSM, HashiCorp Vault 등을 연동할 수 있습니다.

```python
from LLMEngine.core.secrets import set_provider, ChainedSecretProvider

# Vault → 환경 변수 순서로 조회
set_provider(ChainedSecretProvider([VaultProvider(), EnvSecretProvider()]))
```