"""Google Gemini API 어댑터."""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Tuple

from LLMEngine.infrastructure.llm.base_adapter import BaseLLMAdapter, RefusalError
from LLMEngine.core.schemas import ChunkMetadata, LLMInternalResponse, RefinedList
from LLMEngine.application.prompts import (
    SYSTEM_PROMPT, build_user_prompt, AGGREGATOR_SYSTEM_PROMPT,
)

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
    ) -> None:
        if genai is None:
            raise RuntimeError("pip install google-genai 필요")
        super().__init__(
            model=model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            dedup_model=dedup_model or os.getenv("GEMINI_DEDUP_MODEL", "gemini-2.0-flash"),
            max_retries=max_retries, retry_base_delay=retry_base_delay,
            api_timeout_s=api_timeout_s,
        )
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._client: Any | None = None
        self._cached_chunk_config: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aio.aclose()
            self._client = None

    def _chunk_config(self) -> Any:
        if self._cached_chunk_config is None:
            self._cached_chunk_config = genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=LLMInternalResponse,
                automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
            )
        return self._cached_chunk_config

    # ── Hooks ────────────────────────────────────────────────────────

    def _call_chunk_sync(self, chunk_data: ChunkMetadata) -> Any:
        return self._ensure_client().models.generate_content(
            model=self.model,
            contents=build_user_prompt(chunk_data, total_chunks=chunk_data.total_chunks),
            config=self._chunk_config(),
        )

    async def _call_chunk_async(self, chunk_data: ChunkMetadata) -> Any:
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
            br = getattr(response.prompt_feedback, "block_reason", None)
            if br is not None:
                raise RefusalError(f"Gemini 프롬프트 차단: block_reason={br}")
        if not response.candidates:
            raise RuntimeError("Gemini 응답에 candidates가 없습니다.")
        cand = response.candidates[0]
        fr = getattr(cand, "finish_reason", None)
        if fr is not None:
            fs = str(fr).upper()
            if "SAFETY" in fs or "BLOCK" in fs:
                raise RefusalError(f"Gemini safety 차단: finish_reason={fr}")
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return parsed if isinstance(parsed, LLMInternalResponse) else LLMInternalResponse.model_validate(parsed)
        text = response.text
        if not text or not text.strip():
            raise RuntimeError("Gemini 응답 본문이 비어 있습니다.")
        return LLMInternalResponse.model_validate_json(text)

    def _extract_usage(self, response: Any) -> Tuple[int, int, int]:
        um = getattr(response, "usage_metadata", None)
        if not um:
            return 0, 0, 0
        pt = int(getattr(um, "prompt_token_count", None) or 0)
        ct = int(getattr(um, "candidates_token_count", None) or 0)
        tt = int(getattr(um, "total_token_count", None) or (pt + ct))
        return pt, ct, tt

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        key = self.model.lower()
        if key in _GEMINI_COSTS:
            inp, out = _GEMINI_COSTS[key]
        else:
            inp, out = next(
                (pair for name, pair in _GEMINI_COSTS.items() if name in key),
                _DEFAULT_COST,
            )
        cost = (Decimal(prompt_tokens) * inp + Decimal(completion_tokens) * out) / Decimal("1000000")
        return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    def _should_not_retry(self, exc: Exception) -> bool:
        if genai_errors and isinstance(exc, genai_errors.ClientError):
            code = getattr(exc, "code", None)
            if code in (401, 403):
                return True
            if code == 429:
                msg = str(exc).lower()
                if any(kw in msg for kw in ("please retry", "retry in", "retry_delay")):
                    return False
                if "invalid" in msg and "api" in msg:
                    return True
        msg = str(exc).lower()
        if "api key" in msg and "invalid" in msg:
            return True
        if "permission denied" in msg:
            return True
        return False

    def _call_aggregate_sync(self, user_content: str) -> Any:
        client = self._ensure_client()
        config = genai_types.GenerateContentConfig(
            system_instruction=AGGREGATOR_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=RefinedList,
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
        )
        return client.models.generate_content(
            model=self.dedup_model, contents=user_content, config=config,
        )

    def _parse_aggregate_response(self, response: Any) -> RefinedList:
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, RefinedList):
            return parsed
        if parsed is not None:
            return RefinedList.model_validate(parsed)
        return RefinedList.model_validate_json(response.text)
