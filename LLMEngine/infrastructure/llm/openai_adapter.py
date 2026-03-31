"""OpenAI API 어댑터."""

from __future__ import annotations

import asyncio
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Tuple, TYPE_CHECKING

from LLMEngine.infrastructure.llm.base_adapter import BaseLLMAdapter
from LLMEngine.infrastructure.llm.types import OpenAICompletionResponse
from LLMEngine.core.exceptions import RefusalError, TruncatedResponseError
from LLMEngine.core.schemas import ChunkMetadata, LLMInternalResponse, RefinedList

if TYPE_CHECKING:
    from openai import OpenAI as _OpenAI, AsyncOpenAI as _AsyncOpenAI

try:
    from openai import OpenAI, AsyncOpenAI, RateLimitError, AuthenticationError
except ImportError:
    OpenAI = AsyncOpenAI = RateLimitError = AuthenticationError = None

_MODEL_COSTS: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-2024-08-06": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4o": (Decimal("2.50"), Decimal("10.00")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
}
_DEFAULT_COST = (Decimal("2.50"), Decimal("10.00"))


class OpenAIAdapter(BaseLLMAdapter):
    def __init__(
        self,
        model: str = "gpt-4o-2024-08-06",
        dedup_model: str = "gpt-4o-mini",
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        api_key: str | None = None,
        api_timeout_s: float = 120.0,
        max_completion_tokens: int = 2500,
        temperature: float = 1.0,
        seed: int | None = None,
    ) -> None:
        super().__init__(
            model=model, dedup_model=dedup_model,
            max_retries=max_retries, retry_base_delay=retry_base_delay,
            api_timeout_s=api_timeout_s,
            temperature=temperature,
            seed=seed,
        )
        self.max_completion_tokens = max_completion_tokens
        from LLMEngine.core.secrets import get_secret
        self.api_key = api_key or get_secret("OPENAI_API_KEY")
        self._client: _OpenAI | None = None
        self._async_client: _AsyncOpenAI | None = None

    def _validate_sdk(self) -> None:
        if OpenAI is None:
            raise RuntimeError("pip install openai 필요")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")

    def _ensure_client(self) -> Any:
        if self._client is None:
            self._validate_sdk()
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def _ensure_async_client(self) -> Any:
        if self._async_client is None:
            self._validate_sdk()
            self._async_client = AsyncOpenAI(api_key=self.api_key)
        return self._async_client

    async def close(self) -> None:
        if self._async_client is not None:
            await self._async_client.close()
            self._async_client = None
        if self._client is not None:
            if hasattr(self._client, "close"):
                self._client.close()
            self._client = None

    # ── Hooks ────────────────────────────────────────────────────────

    def _build_chat_kwargs(
        self, *, model: str, system: str, user: str,
        response_format: Any, max_tokens: int | None = None,
        timeout: bool = True,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = dict(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format=response_format,
            temperature=self.temperature,
        )
        if max_tokens is not None:
            kwargs["max_completion_tokens"] = max_tokens
        if timeout:
            kwargs["timeout"] = self.api_timeout_s
        if self.seed is not None:
            kwargs["seed"] = self.seed
        return kwargs

    def _call_chunk_sync(self, chunk_data: ChunkMetadata) -> Any:
        from LLMEngine.application.prompts import SYSTEM_PROMPT, build_user_prompt
        kwargs = self._build_chat_kwargs(
            model=self.model, system=SYSTEM_PROMPT,
            user=build_user_prompt(chunk_data, total_chunks=chunk_data.total_chunks),
            response_format=LLMInternalResponse,
            max_tokens=self.max_completion_tokens,
        )
        return self._ensure_client().beta.chat.completions.parse(**kwargs)

    async def _call_chunk_async(self, chunk_data: ChunkMetadata) -> Any:
        from LLMEngine.application.prompts import SYSTEM_PROMPT, build_user_prompt
        kwargs = self._build_chat_kwargs(
            model=self.model, system=SYSTEM_PROMPT,
            user=build_user_prompt(chunk_data, total_chunks=chunk_data.total_chunks),
            response_format=LLMInternalResponse,
            max_tokens=self.max_completion_tokens, timeout=False,
        )
        return await asyncio.wait_for(
            self._ensure_async_client().beta.chat.completions.parse(**kwargs),
            timeout=self.api_timeout_s,
        )

    @staticmethod
    def _extract_parsed(response: Any, *, check_truncation: bool = False, label: str = "") -> Any:
        """choices → refusal → parsed 공통 검증."""
        prefix = f"{label} " if label else ""
        if not getattr(response, "choices", None):
            raise RuntimeError(f"{prefix}OpenAI 응답에 choices가 없습니다.")
        choice = response.choices[0]
        if check_truncation and getattr(choice, "finish_reason", None) == "length":
            raise TruncatedResponseError(
                "응답이 max_completion_tokens에 도달하여 잘렸습니다. "
                "max_completion_tokens 증가가 필요합니다."
            )
        message = choice.message
        if getattr(message, "refusal", None):
            raise RefusalError(f"{prefix}모델 거부: {message.refusal}")
        parsed = getattr(message, "parsed", None)
        if parsed is None:
            raise RuntimeError(f"{prefix}구조화 출력 파싱 결과가 비어 있습니다.")
        return parsed

    def _parse_structured_response(self, completion: Any) -> LLMInternalResponse:
        return self._extract_parsed(completion, check_truncation=True)

    def _extract_usage(self, response: Any) -> Tuple[int, int, int]:
        usage = getattr(response, "usage", None)
        if not usage:
            return 0, 0, 0
        return usage.prompt_tokens, usage.completion_tokens, usage.total_tokens

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        inp, out = _MODEL_COSTS.get(self.model, _DEFAULT_COST)
        cost = (Decimal(prompt_tokens) * inp + Decimal(completion_tokens) * out) / Decimal("1000000")
        return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    def _should_not_retry(self, exc: Exception) -> bool:
        if RateLimitError and isinstance(exc, RateLimitError):
            msg = str(exc).lower()
            if "insufficient_quota" in msg or "exceeded your current quota" in msg:
                return True
        if AuthenticationError and isinstance(exc, AuthenticationError):
            return True
        return False

    def _call_aggregate_sync(self, user_content: str) -> Any:
        from LLMEngine.application.prompts import AGGREGATOR_SYSTEM_PROMPT
        kwargs = self._build_chat_kwargs(
            model=self.dedup_model, system=AGGREGATOR_SYSTEM_PROMPT,
            user=user_content, response_format=RefinedList,
        )
        return self._ensure_client().beta.chat.completions.parse(**kwargs)

    def _parse_aggregate_response(self, response: Any) -> RefinedList:
        return self._extract_parsed(response, label="Aggregate")
