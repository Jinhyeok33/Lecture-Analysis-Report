"""Google Gemini API 어댑터."""

from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Tuple, TYPE_CHECKING

from LLMEngine.infrastructure.llm.base_adapter import BaseLLMAdapter
from LLMEngine.core.exceptions import RefusalError, TruncatedResponseError
from LLMEngine.core.schemas import ChunkMetadata, LLMInternalResponse, RefinedList

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
            raise RuntimeError("pip install google-genai 필요")
        if seed is not None:
            logger.warning("Gemini API는 seed 파라미터를 지원하지 않습니다. seed=%d 무시됨.", seed)
        super().__init__(
            model=model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            dedup_model=dedup_model or os.getenv("GEMINI_DEDUP_MODEL", "gemini-2.0-flash"),
            max_retries=max_retries, retry_base_delay=retry_base_delay,
            api_timeout_s=api_timeout_s,
            temperature=temperature,
        )
        from LLMEngine.core.secrets import get_secret
        self.api_key = api_key or get_secret("GEMINI_API_KEY")
        self.max_completion_tokens = max_completion_tokens
        self._client: _GeminiClient | None = None
        self._cached_chunk_config: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
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
            from LLMEngine.application.prompts import SYSTEM_PROMPT
            self._cached_chunk_config = genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=LLMInternalResponse,
                max_output_tokens=self.max_completion_tokens,
                temperature=self.temperature,
                automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
            )
        return self._cached_chunk_config

    # ── Hooks ────────────────────────────────────────────────────────

    def _call_chunk_sync(self, chunk_data: ChunkMetadata) -> Any:
        from LLMEngine.application.prompts import build_user_prompt
        return self._ensure_client().models.generate_content(
            model=self.model,
            contents=build_user_prompt(chunk_data, total_chunks=chunk_data.total_chunks),
            config=self._chunk_config(),
        )

    async def _call_chunk_async(self, chunk_data: ChunkMetadata) -> Any:
        from LLMEngine.application.prompts import build_user_prompt
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
            if "MAX_TOKENS" in fs or "LENGTH" in fs:
                raise TruncatedResponseError(
                    f"Gemini 응답이 토큰 한도에 도달하여 잘렸습니다 (finish_reason={fr}). "
                    "max_completion_tokens 증가가 필요합니다."
                )
        text = getattr(response, "text", None)
        if not getattr(response, "parsed", None) and (not text or not text.strip()):
            raise RuntimeError("Gemini 응답 본문이 비어 있습니다.")
        return self._parse_gemini_response(response, LLMInternalResponse)

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
        from LLMEngine.application.prompts import AGGREGATOR_SYSTEM_PROMPT
        client = self._ensure_client()
        config = genai_types.GenerateContentConfig(
            system_instruction=AGGREGATOR_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=RefinedList,
            temperature=self.temperature,
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
        )
        return client.models.generate_content(
            model=self.dedup_model, contents=user_content, config=config,
        )

    def _parse_aggregate_response(self, response: Any) -> RefinedList:
        return self._parse_gemini_response(response, RefinedList)

    @staticmethod
    def _parse_gemini_response(response: Any, target_type: type) -> Any:
        """Gemini 응답에서 target_type 인스턴스를 추출하는 공통 로직."""
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, target_type):
            return parsed
        if parsed is not None:
            return target_type.model_validate(parsed)
        return target_type.model_validate_json(response.text)
