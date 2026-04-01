"""SDK 응답 타입을 런타임 의존 없이 정의하는 Protocol 모음."""

from __future__ import annotations

from typing import Any, Protocol, Sequence, runtime_checkable


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
