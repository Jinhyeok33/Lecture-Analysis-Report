"""OpenAI 연동 어댑터 및 통합 처리 Fallback 모듈."""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, List

logger = logging.getLogger(__name__)

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
    from openai import OpenAI, AsyncOpenAI
    from openai import RateLimitError, APIError, AuthenticationError
except ImportError:
    OpenAI = None
    AsyncOpenAI = None
    RateLimitError = None
    APIError = None
    AuthenticationError = None

from src.llm_engine.core.ports import ILLMProvider
from src.llm_engine.core.schemas import ChunkMetadata, ChunkResult, LLMInternalResponse, RefinedList
from src.llm_engine.application.prompts import (
    SYSTEM_PROMPT, build_user_prompt,
    AGGREGATOR_SYSTEM_PROMPT, build_aggregator_refine_prompt
)
from src.llm_engine.application.validation import validate_evidence

AGGREGATOR_MAX_ITEMS = 200

class OpenAIAdapter(ILLMProvider):
    similarity_threshold = 0.82

    def __init__(
        self,
        model: str = "gpt-4o-2024-08-06",
        dedup_model: str = "gpt-4o-mini",
        client: Any | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        api_key: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = client
        self._async_client = None 
        self.model = model
        self.dedup_model = dedup_model
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay

    @property
    def async_client(self):
        if self._async_client is None:
            if AsyncOpenAI is None:
                raise RuntimeError("AsyncOpenAI를 사용할 수 없습니다.")
            self._async_client = AsyncOpenAI(api_key=self.api_key, timeout=120.0)
        return self._async_client

    def analyze_chunk(self, chunk_data: ChunkMetadata) -> ChunkResult:
        wrapper_response = self._request_structured_output(chunk_data)
        payload = wrapper_response.final_output
        validated_evidence = validate_evidence(payload.evidence, chunk_data.text)
        
        return ChunkResult(
            chunk_id=chunk_data.chunk_id,
            start_time=chunk_data.start_time,
            end_time=chunk_data.end_time,
            scores=payload.scores,
            strengths=payload.strengths,
            issues=payload.issues,
            evidence=validated_evidence,
        )

    async def analyze_chunk_async(self, chunk_data: ChunkMetadata) -> ChunkResult:
        wrapper_response = await self._request_structured_output_async(chunk_data)
        payload = wrapper_response.final_output
        validated_evidence = validate_evidence(payload.evidence, chunk_data.text)
        
        return ChunkResult(
            chunk_id=chunk_data.chunk_id,
            start_time=chunk_data.start_time,
            end_time=chunk_data.end_time,
            scores=payload.scores,
            strengths=payload.strengths,
            issues=payload.issues,
            evidence=validated_evidence,
        )

    def _request_structured_output(self, chunk_data: ChunkMetadata) -> LLMInternalResponse:
        if self.client is None:
            if OpenAI is None:
                raise RuntimeError("OpenAI 클라이언트를 사용할 수 없습니다.")
            self.client = OpenAI(api_key=self.api_key) if self.api_key else OpenAI()

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                start_time = time.perf_counter()
                completion = self.client.beta.chat.completions.parse(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": build_user_prompt(chunk_data)},
                    ],
                    response_format=LLMInternalResponse,
                )
                elapsed = time.perf_counter() - start_time
                logger.info("[Chunk %02d] LLM 추론 완료 (Attempt %d): %.2f초 소요", chunk_data.chunk_id, attempt, elapsed)
                
                parsed = self._extract_wrapper(completion)
                validate_evidence(parsed.final_output.evidence, chunk_data.text)
                return parsed
                
            except ValueError as exc:
                if "환각 감지" in str(exc):
                    last_error = exc
                    logger.warning(f"[Chunk {chunk_data.chunk_id}] 환각 감지 (시도 {attempt}): {exc}")
                    if attempt == self.max_retries:
                        break
                    sleep_time = self.retry_base_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 1.5)
                    time.sleep(sleep_time)
                    continue
                raise
            except Exception as exc:
                last_error = exc
                if self._should_not_retry(exc):
                    raise RuntimeError(f"재시도 불가 오류: {exc}") from exc
                if attempt == self.max_retries:
                    break
                sleep_time = self.retry_base_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 1.5)
                time.sleep(sleep_time)

        raise RuntimeError(f"{self.max_retries}회 시도 후 실패. 마지막 오류: {last_error}") from last_error

    async def _request_structured_output_async(self, chunk_data: ChunkMetadata) -> LLMInternalResponse:
        client = self.async_client
        last_error: Exception | None = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                await asyncio.sleep(0.1)
                completion = await client.beta.chat.completions.parse(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": build_user_prompt(chunk_data)},
                    ],
                    response_format=LLMInternalResponse,
                )
                parsed = self._extract_wrapper(completion)
                validate_evidence(parsed.final_output.evidence, chunk_data.text)
                return parsed
            except ValueError as exc:
                if "환각 감지" in str(exc):
                    last_error = exc
                    logger.warning(f"[Chunk {chunk_data.chunk_id}] 환각 감지 (Async 시도 {attempt}): {exc}")
                    if attempt == self.max_retries:
                        break
                    await asyncio.sleep(self.retry_base_delay * attempt)
                    continue
                raise
            except Exception as exc:
                last_error = exc
                if self._should_not_retry(exc):
                    raise RuntimeError(f"재시도 불가 오류: {exc}") from exc
                if attempt == self.max_retries:
                    break
                await asyncio.sleep(self.retry_base_delay * attempt)
                
        raise RuntimeError(f"연결 실패 (최대 재시도 초과): {last_error}") from last_error

    def _extract_wrapper(self, completion: Any) -> LLMInternalResponse:
        if not getattr(completion, "choices", None):
            raise RuntimeError("OpenAI 응답에 choices가 없습니다.")
        message = completion.choices[0].message
        if getattr(message, "refusal", None):
            raise RuntimeError(f"모델이 요청을 거부함: {message.refusal}")
        parsed = getattr(message, "parsed", None)
        if parsed is None:
            raise RuntimeError("구조화 출력 파싱 결과가 비어 있습니다.")
        return parsed

    def _should_not_retry(self, exc: Exception) -> bool:
        if RateLimitError and isinstance(exc, RateLimitError):
            error_str = str(exc).lower()
            if "insufficient_quota" in error_str or "exceeded your current quota" in error_str:
                return True
        if AuthenticationError and isinstance(exc, AuthenticationError):
            return True
        return False

    def aggregate_results(self, items: List[str], label: str, scores_context: str, trends: str) -> List[str]:
        if self.client is None:
            if OpenAI is None:
                raise RuntimeError("OpenAI 클라이언트를 사용할 수 없습니다.")
            self.client = OpenAI(api_key=self.api_key) if self.api_key else OpenAI()

        try:
            resp = self.client.beta.chat.completions.parse(
                model=self.dedup_model,
                messages=[
                    {"role": "system", "content": AGGREGATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": build_aggregator_refine_prompt(items[:AGGREGATOR_MAX_ITEMS], label, scores_context, trends)},
                ],
                response_format=RefinedList,
            )
            
            result_items = resp.choices[0].message.parsed.items
            
            # [수정] LLM이 지시를 어기고 8개 미만으로 뽑았을 경우, 에러 방지를 위해 Fallback 데이터 꽂아넣기
            if len(result_items) < 8:
                result_items.extend(self._deduplicate_ranked_strings(items)[:8 - len(result_items)])
                
            return result_items
        except Exception as e:
            logger.warning("LLM 통합 요약 실패: %s; 어휘 기반 중복 제거로 대체합니다.", e)
            return self._deduplicate_ranked_strings(items)[:15]

    def _deduplicate_ranked_strings(self, values: List[str]) -> List[str]:
        if not values:
            return ["전체 평가 점수를 기반으로 도출된 추가 특이사항이 없습니다."] * 8

        counts = Counter(value.strip() for value in values if value.strip())
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        deduplicated: List[str] = []

        for candidate, _ in ranked:
            if any(self._is_similar(candidate, existing) for existing in deduplicated):
                continue
            deduplicated.append(candidate)
        return deduplicated

    def _is_similar(self, left: str, right: str) -> bool:
        return SequenceMatcher(None, left, right).ratio() >= self.similarity_threshold
