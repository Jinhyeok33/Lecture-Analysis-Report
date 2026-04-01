"""LLMEngine 전용 예외 계층."""


class RefusalError(RuntimeError):
    """모델이 요청을 거부해 재시도해도 해결되지 않는 오류."""


class HallucinationError(ValueError):
    """Evidence 환각 감지로 재시도 가능한 오류."""


class LanguageViolationError(ValueError):
    """응답에 한국어 외 언어가 섞여 있는 오류."""


class CotMismatchError(ValueError):
    """CoT 점수와 final_output 점수가 불일치하는 오류."""


class TruncatedResponseError(ValueError):
    """max_completion_tokens 도달로 응답이 잘린 오류."""


class NonRetryableAPIError(RuntimeError):
    """인증 실패, 쿼터 초과 등 재시도 불가 API 오류."""
