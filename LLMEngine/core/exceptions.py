"""LLMEngine 전용 예외 계층.

모든 모듈에서 import할 수 있도록 core 계층에 배치하여 순환 참조를 방지한다.
"""


class RefusalError(RuntimeError):
    """모델이 요청을 거부 — 재시도 불가, 입력/프롬프트 수정 필요."""


class HallucinationError(ValueError):
    """evidence 환각 감지 — 재시도로 해결 가능."""


class LanguageViolationError(ValueError):
    """응답에 한국어 외 언어 혼입 — 재시도로 해결 가능."""


class CotMismatchError(ValueError):
    """CoT 점수와 final_output 점수 불일치 — 재시도로 해결 가능."""


class TruncatedResponseError(ValueError):
    """max_completion_tokens 도달로 응답 잘림 — 재시도 불가, 설정 변경 필요."""


class NonRetryableAPIError(RuntimeError):
    """인증 실패, 쿼터 초과 등 재시도 불가 API 에러."""
