"""Google Gemini-backed adapter for the shared LLM engine."""

from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, Any, Tuple

from src.llm_engine.core.exceptions import RefusalError, TruncatedResponseError
from src.llm_engine.core.schemas import ChunkMetadata, LLMInternalResponse, RefinedList
from src.llm_engine.core.secrets import get_secret
from src.llm_engine.infrastructure.llm.base_adapter import BaseLLMAdapter

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from google.genai import Client as _GeminiClient

try:
    from google import genai
    from google.genai import errors as genai_errors, types as genai_types
except ImportError:
    genai = genai_errors = genai_types = None

_GEMINI_COSTS: dict[str, tuple[Decimal, Decimal]] = {
    "gemini-2.0-flash": (Decimal("0.10"), Decimal("0.40")),
    "gemini-2.0-flash-001": (Decimal("0.10"), Decimal("0.40")),
    "gemini-1.5-flash": (Decimal("0.075"), Decimal("0.30")),
    "gemini-1.5-flash-latest": (Decimal("0.075"), Decimal("0.30")),
    "gemini-1.5-pro": (Decimal("1.25"), Decimal("5.00")),
}
_DEFAULT_COST = (Decimal("0.10"), Decimal("0.40"))


class GeminiAdapter(BaseLLMAdapter):
    def __init__(
        self,
        model: str | None = None,
        dedup_model: str | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        api_key: str | None = None,
        api_timeout_s: float = 120.0,
        max_completion_tokens: int = 2500,
        temperature: float = 1.0,
        seed: int | None = None,
    ) -> None:
        if genai is None:
            raise RuntimeError("pip install google-genai is required")
        if seed is not None:
            logger.warning("Gemini does not support seed; ignoring seed=%d", seed)
        super().__init__(
            model=model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            dedup_model=dedup_model or os.getenv("GEMINI_DEDUP_MODEL", "gemini-2.0-flash"),
            max_retries=max_retries,
            retry_base_delay=retry_base_delay,
            api_timeout_s=api_timeout_s,
            temperature=temperature,
        )
        self.api_key = api_key or get_secret("GEMINI_API_KEY")
        self.max_completion_tokens = max_completion_tokens
        self._client: _GeminiClient | None = None
        self._cached_chunk_config: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("GEMINI_API_KEY is not configured")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aio.aclose()
            except Exception:
                pass
            self._client = None

    def _chunk_config(self) -> Any:
        if self._cached_chunk_config is None:
            from src.llm_engine.application.prompts import SYSTEM_PROMPT

            self._cached_chunk_config = genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=LLMInternalResponse,
                max_output_tokens=self.max_completion_tokens,
                temperature=self.temperature,
                automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
            )
        return self._cached_chunk_config

    def _call_chunk_sync(self, chunk_data: ChunkMetadata) -> Any:
        from src.llm_engine.application.prompts import build_user_prompt

        return self._ensure_client().models.generate_content(
            model=self.model,
            contents=build_user_prompt(chunk_data, total_chunks=chunk_data.total_chunks),
            config=self._chunk_config(),
        )

    async def _call_chunk_async(self, chunk_data: ChunkMetadata) -> Any:
        from src.llm_engine.application.prompts import build_user_prompt

        client = self._ensure_client()
        return await asyncio.wait_for(
            client.aio.models.generate_content(
                model=self.model,
                contents=build_user_prompt(chunk_data, total_chunks=chunk_data.total_chunks),
                config=self._chunk_config(),
            ),
            timeout=self.api_timeout_s,
        )

    def _parse_structured_response(self, response: Any) -> LLMInternalResponse:
        if response.prompt_feedback is not None:
            block_reason = getattr(response.prompt_feedback, "block_reason", None)
            if block_reason is not None:
                raise RefusalError(f"Gemini prompt blocked: {block_reason}")
        if not response.candidates:
            raise RuntimeError("Gemini response returned no candidates")
        candidate = response.candidates[0]
        finish_reason = getattr(candidate, "finish_reason", None)
        if finish_reason is not None:
            reason = str(finish_reason).upper()
            if "SAFETY" in reason or "BLOCK" in reason:
                raise RefusalError(f"Gemini safety block: {finish_reason}")
            if "MAX_TOKENS" in reason or "LENGTH" in reason:
                raise TruncatedResponseError(
                    "Gemini response hit the token limit; increase max_completion_tokens"
                )
        text = getattr(response, "text", None)
        if not getattr(response, "parsed", None) and (not text or not text.strip()):
            raise RuntimeError("Gemini response body is empty")
        return self._parse_gemini_response(response, LLMInternalResponse)

    def _extract_usage(self, response: Any) -> Tuple[int, int, int]:
        usage = getattr(response, "usage_metadata", None)
        if not usage:
            return 0, 0, 0
        prompt_tokens = int(getattr(usage, "prompt_token_count", None) or 0)
        completion_tokens = int(getattr(usage, "candidates_token_count", None) or 0)
        total_tokens = int(getattr(usage, "total_token_count", None) or (prompt_tokens + completion_tokens))
        return prompt_tokens, completion_tokens, total_tokens

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        key = self.model.lower()
        if key in _GEMINI_COSTS:
            input_cost, output_cost = _GEMINI_COSTS[key]
        else:
            input_cost, output_cost = next(
                (pair for name, pair in _GEMINI_COSTS.items() if name in key),
                _DEFAULT_COST,
            )
        cost = (Decimal(prompt_tokens) * input_cost + Decimal(completion_tokens) * output_cost) / Decimal("1000000")
        return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    def _should_not_retry(self, exc: Exception) -> bool:
        if genai_errors and isinstance(exc, genai_errors.ClientError):
            code = getattr(exc, "code", None)
            if code in (401, 403):
                return True
            if code == 429:
                message = str(exc).lower()
                if any(keyword in message for keyword in ("please retry", "retry in", "retry_delay")):
                    return False
                if "invalid" in message and "api" in message:
                    return True
        message = str(exc).lower()
        if "api key" in message and "invalid" in message:
            return True
        if "permission denied" in message:
            return True
        return False

    def _call_aggregate_sync(self, user_content: str) -> Any:
        from src.llm_engine.application.prompts import AGGREGATOR_SYSTEM_PROMPT

        client = self._ensure_client()
        config = genai_types.GenerateContentConfig(
            system_instruction=AGGREGATOR_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=RefinedList,
            temperature=self.temperature,
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
        )
        return client.models.generate_content(
            model=self.dedup_model,
            contents=user_content,
            config=config,
        )

    def _parse_aggregate_response(self, response: Any) -> RefinedList:
        return self._parse_gemini_response(response, RefinedList)

    @staticmethod
    def _parse_gemini_response(response: Any, target_type: type) -> Any:
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, target_type):
            return parsed
        if parsed is not None:
            return target_type.model_validate(parsed)
        return target_type.model_validate_json(response.text)
