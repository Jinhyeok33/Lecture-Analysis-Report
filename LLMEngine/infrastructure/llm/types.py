"""SDK 응답 타입을 런타임 의존 없이 정의하는 Protocol 모음.

openai/google-genai SDK를 import하지 않고도 타입 검사를 지원하기 위해
structural subtyping(Protocol)을 사용한다.
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence, runtime_checkable


# ── OpenAI SDK 응답 프로토콜 ─────────────────────────────────────────

class OpenAIUsage(Protocol):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class OpenAIMessage(Protocol):
    @property
    def refusal(self) -> str | None: ...
    @property
    def parsed(self) -> Any: ...


class OpenAIChoice(Protocol):
    @property
    def finish_reason(self) -> str | None: ...
    @property
    def message(self) -> OpenAIMessage: ...


@runtime_checkable
class OpenAICompletionResponse(Protocol):
    @property
    def choices(self) -> Sequence[OpenAIChoice]: ...
    @property
    def usage(self) -> OpenAIUsage | None: ...


# ── Gemini SDK 응답 프로토콜 ─────────────────────────────────────────

class GeminiPromptFeedback(Protocol):
    @property
    def block_reason(self) -> Any: ...


class GeminiCandidate(Protocol):
    @property
    def finish_reason(self) -> Any: ...


class GeminiUsageMetadata(Protocol):
    @property
    def prompt_token_count(self) -> int | None: ...
    @property
    def candidates_token_count(self) -> int | None: ...
    @property
    def total_token_count(self) -> int | None: ...


@runtime_checkable
class GeminiContentResponse(Protocol):
    @property
    def prompt_feedback(self) -> GeminiPromptFeedback | None: ...
    @property
    def candidates(self) -> Sequence[GeminiCandidate]: ...
    @property
    def text(self) -> str | None: ...
    @property
    def parsed(self) -> Any: ...
    @property
    def usage_metadata(self) -> GeminiUsageMetadata | None: ...
