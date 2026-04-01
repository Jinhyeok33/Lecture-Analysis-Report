"""OpenAI-backed LLM adapter."""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, TYPE_CHECKING, Tuple, cast

from src.llm_engine.core.exceptions import RefusalError, TruncatedResponseError
from src.llm_engine.core.secrets import get_secret
from src.llm_engine.core.schemas import ChunkMetadata, LLMInternalResponse, RefinedList
from src.llm_engine.infrastructure.llm.base_adapter import BaseLLMAdapter
from src.llm_engine.infrastructure.llm.types import OpenAICompletionResponse

if TYPE_CHECKING:
    from openai import AsyncOpenAI as _AsyncOpenAI
    from openai import OpenAI as _OpenAI

try:
    from dotenv import load_dotenv

    current_dir = Path(__file__).resolve().parent
    while current_dir != current_dir.parent:
        env_file = current_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            break
        current_dir = current_dir.parent
except ImportError:
    load_dotenv = None

try:
    from openai import AsyncOpenAI, AuthenticationError, OpenAI, RateLimitError
except ImportError:
    OpenAI = None
    AsyncOpenAI = None
    RateLimitError = None
    AuthenticationError = None

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
            model=model,
            dedup_model=dedup_model,
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
            api_timeout_s=api_timeout_s,
            temperature=temperature,
            seed=seed,
        )
        self.max_completion_tokens = max_completion_tokens
        self.api_key = api_key or get_secret("OPENAI_API_KEY")
        self._client: _OpenAI | None = None
        self._async_client: _AsyncOpenAI | None = None

    def _validate_sdk(self) -> None:
        if OpenAI is None or AsyncOpenAI is None:
            raise RuntimeError("pip install openai is required")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

    def _ensure_client(self) -> Any:
        if self._client is None:
            self._validate_sdk()
            self._client = OpenAI(api_key=self.api_key, timeout=self.api_timeout_s)
        return self._client

    def _ensure_async_client(self) -> Any:
        if self._async_client is None:
            self._validate_sdk()
            self._async_client = AsyncOpenAI(api_key=self.api_key, timeout=self.api_timeout_s)
        return self._async_client

    async def close(self) -> None:
        if self._async_client is not None:
            await self._async_client.close()
            self._async_client = None
        if self._client is not None:
            if hasattr(self._client, "close"):
                self._client.close()
            self._client = None

    def _build_chat_kwargs(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_format: Any,
        max_tokens: int | None = None,
        include_timeout: bool = True,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": response_format,
            "temperature": self.temperature,
        }
        if max_tokens is not None:
            kwargs["max_completion_tokens"] = max_tokens
        if include_timeout:
            kwargs["timeout"] = self.api_timeout_s
        if self.seed is not None:
            kwargs["seed"] = self.seed
        return kwargs

    def _call_chunk_sync(self, chunk_data: ChunkMetadata) -> Any:
        from src.llm_engine.application.prompts import SYSTEM_PROMPT, build_user_prompt

        kwargs = self._build_chat_kwargs(
            model=self.model,
            system=SYSTEM_PROMPT,
            user=build_user_prompt(chunk_data, total_chunks=chunk_data.total_chunks),
            response_format=LLMInternalResponse,
            max_tokens=self.max_completion_tokens,
        )
        return self._ensure_client().beta.chat.completions.parse(**kwargs)

    async def _call_chunk_async(self, chunk_data: ChunkMetadata) -> Any:
        from src.llm_engine.application.prompts import SYSTEM_PROMPT, build_user_prompt

        kwargs = self._build_chat_kwargs(
            model=self.model,
            system=SYSTEM_PROMPT,
            user=build_user_prompt(chunk_data, total_chunks=chunk_data.total_chunks),
            response_format=LLMInternalResponse,
            max_tokens=self.max_completion_tokens,
            include_timeout=False,
        )
        return await asyncio.wait_for(
            self._ensure_async_client().beta.chat.completions.parse(**kwargs),
            timeout=self.api_timeout_s,
        )

    @staticmethod
    def _extract_parsed(
        response: OpenAICompletionResponse,
        *,
        check_truncation: bool = False,
        label: str = "",
    ) -> Any:
        prefix = f"{label} " if label else ""
        if not getattr(response, "choices", None):
            raise RuntimeError(f"{prefix}OpenAI response has no choices")

        choice = response.choices[0]
        if check_truncation and getattr(choice, "finish_reason", None) == "length":
            raise TruncatedResponseError(
                "Response reached max_completion_tokens and was truncated"
            )

        message = choice.message
        if getattr(message, "refusal", None):
            raise RefusalError(f"{prefix}model refusal: {message.refusal}")

        parsed = getattr(message, "parsed", None)
        if parsed is None:
            raise RuntimeError(f"{prefix}structured parse result is empty")
        return parsed

    def _parse_structured_response(self, response: Any) -> LLMInternalResponse:
        return cast(LLMInternalResponse, self._extract_parsed(cast(OpenAICompletionResponse, response), check_truncation=True))

    def _extract_usage(self, response: Any) -> Tuple[int, int, int]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return 0, 0, 0
        return usage.prompt_tokens, usage.completion_tokens, usage.total_tokens

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        input_cost, output_cost = _MODEL_COSTS.get(self.model, _DEFAULT_COST)
        cost = (
            Decimal(prompt_tokens) * input_cost
            + Decimal(completion_tokens) * output_cost
        ) / Decimal("1000000")
        return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    def _should_not_retry(self, exc: Exception) -> bool:
        if RateLimitError and isinstance(exc, RateLimitError):
            lowered = str(exc).lower()
            if "insufficient_quota" in lowered or "exceeded your current quota" in lowered:
                return True
        if AuthenticationError and isinstance(exc, AuthenticationError):
            return True
        return False

    def _call_aggregate_sync(self, user_content: str) -> Any:
        from src.llm_engine.application.prompts import AGGREGATOR_SYSTEM_PROMPT

        kwargs = self._build_chat_kwargs(
            model=self.dedup_model,
            system=AGGREGATOR_SYSTEM_PROMPT,
            user=user_content,
            response_format=RefinedList,
        )
        return self._ensure_client().beta.chat.completions.parse(**kwargs)

    def _parse_aggregate_response(self, response: Any) -> RefinedList:
        return cast(RefinedList, self._extract_parsed(cast(OpenAICompletionResponse, response), label="Aggregate"))
