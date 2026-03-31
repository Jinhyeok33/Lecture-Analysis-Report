# 프롬프트 외부 파일 가이드

## 사용법

1. 이 디렉토리에 `{version}.yaml` 파일을 생성합니다.
2. `batch_processor`나 `test_runner` 실행 시 해당 버전이 자동 로딩됩니다.
3. YAML 파일이 없으면 코드 내장 프롬프트(prompts.py)가 사용됩니다.

## YAML 구조

```yaml
# v4.3.yaml 예시
version: "v4.3"
author: "교육 평가팀"
description: "IT 부트캠프 강의 품질 평가 프롬프트"

system_prompt: |
  당신은 IT 부트캠프 강의 품질을 평가하는 10년 차 수석 교육 평가관입니다.
  ...

aggregator_system_prompt: |
  당신은 IT 교육 강의 품질 리포트를 최종 정리하는 수석 에디터입니다.
  ...
```

## A/B 테스트

1. `v4.3.yaml`과 `v4.4.yaml`을 각각 생성
2. `prompts.py`의 `PROMPT_VERSION`을 변경하거나 환경 변수 `LLM_PROMPT_VERSION`으로 지정
3. 동일 스크립트로 두 버전을 실행하여 결과 비교

## 주의사항

- `pyyaml` 패키지가 필요합니다: `pip install pyyaml`
- YAML 파일이 없으면 코드 내장 프롬프트로 자동 fallback됩니다.
