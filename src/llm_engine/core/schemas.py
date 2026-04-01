"""LLM 분석 엔진용 Pydantic 스키마."""

from __future__ import annotations

import logging
from decimal import Decimal
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

_schema_logger = logging.getLogger(__name__)


class ChunkStatus(str, Enum):
    """청크 분석 결과 상태 코드."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUSED = "REFUSED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


class FailureClass(str, Enum):
    """FAILED일 때 재시도 가능성을 세분화한 코드."""

    RETRYABLE = "RETRYABLE"
    NON_RETRYABLE = "NON_RETRYABLE"
    PERMANENT = "PERMANENT"


class TokenUsage(BaseModel):
    """LLM 호출별 토큰 및 비용 메타데이터."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: Decimal = Field(default=Decimal("0"), description="추정 비용 (USD)")
    llm_call_count: int = 0

    @field_serializer("estimated_cost_usd")
    def serialize_cost(self, value: Decimal) -> str:
        return f"{value:.6f}"

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            estimated_cost_usd=self.estimated_cost_usd + other.estimated_cost_usd,
            llm_call_count=self.llm_call_count + other.llm_call_count,
        )


SCHEMA_VERSION = "2"
CHECKPOINT_VERSION = "1"


class ReliabilityMetrics(BaseModel):
    """분석 결과 신뢰도 수치. 0에 가까울수록 불안정, 1에 가까울수록 신뢰."""

    evidence_pass_ratio: float = Field(1.0, ge=0.0, le=1.0)
    hallucination_retries: int = Field(0, ge=0)
    avg_evidence_similarity: float = Field(100.0, ge=0.0, le=100.0)
    score_evidence_consistency: float = Field(1.0, ge=0.0, le=1.0)
    overall_reliability_score: float = Field(1.0, ge=0.0, le=1.0)


class RunMetadata(BaseModel):
    """강의 1건 처리 단위의 운영 메타데이터."""

    schema_version: str = SCHEMA_VERSION
    checkpoint_version: str = CHECKPOINT_VERSION
    prompt_version: str = "unknown"
    model: str = "unknown"
    run_id: Optional[str] = None
    input_hash: Optional[str] = None
    config_hash: Optional[str] = None
    total_chunks: int = 0
    scored_chunks: int = 0
    successful_chunks: int = 0
    fallback_chunks: int = 0
    refused_chunks: int = 0
    failed_chunks: int = 0
    evidence_count_total: int = 0
    total_elapsed_ms: Optional[int] = Field(None, ge=0)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    reliability: ReliabilityMetrics = Field(default_factory=ReliabilityMetrics)


VALID_ITEMS = {
    "learning_objective_intro",
    "previous_lesson_linkage",
    "explanation_sequence",
    "key_point_emphasis",
    "closing_summary",
    "concept_definition",
    "analogy_example_usage",
    "prerequisite_check",
    "example_appropriateness",
    "practice_transition",
    "error_handling",
    "participation_induction",
    "question_response_sufficiency",
}

CATEGORY_TO_DEFAULT_ITEM = {
    "lecture_structure": "explanation_sequence",
    "concept_clarity": "concept_definition",
    "practice_linkage": "practice_transition",
    "interaction": "participation_induction",
}

NA_CAPABLE_ITEMS = {"learning_objective_intro", "previous_lesson_linkage", "closing_summary"}
PREVIOUS_CHUNK_TAIL_MAX_CHARS = 1500


def _normalize_item_key(value: Any) -> str:
    if not isinstance(value, str):
        value = str(value)
    return value.strip().lower().replace(" ", "_").replace("-", "_")


class ScoreBase(BaseModel):
    @field_validator("*")
    @classmethod
    def validate_score_range(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        if not 1 <= value <= 5:
            raise ValueError("점수는 1~5 사이여야 합니다.")
        return value


class FloatScoreBase(BaseModel):
    @field_validator("*")
    @classmethod
    def validate_score_range(cls, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        if not 1.0 <= value <= 5.0:
            raise ValueError("통합 점수는 1.0~5.0 사이여야 합니다.")
        return round(value, 1)


_SCORE_FIELD = Field(ge=1, le=5, description="1~5점 척도")
_SCORE_FIELD_OPTIONAL = Field(None, ge=1, le=5, description="1~5점 척도. N/A 시 null")


class LectureStructureScores(ScoreBase):
    learning_objective_intro: Optional[int] = _SCORE_FIELD_OPTIONAL
    previous_lesson_linkage: Optional[int] = _SCORE_FIELD_OPTIONAL
    explanation_sequence: int = _SCORE_FIELD
    key_point_emphasis: int = _SCORE_FIELD
    closing_summary: Optional[int] = _SCORE_FIELD_OPTIONAL


class ConceptClarityScores(ScoreBase):
    concept_definition: int = _SCORE_FIELD
    analogy_example_usage: int = _SCORE_FIELD
    prerequisite_check: int = _SCORE_FIELD


class PracticeLinkageScores(ScoreBase):
    example_appropriateness: int = _SCORE_FIELD
    practice_transition: int = _SCORE_FIELD
    error_handling: int = _SCORE_FIELD


class InteractionScores(ScoreBase):
    participation_induction: int = _SCORE_FIELD
    question_response_sufficiency: int = _SCORE_FIELD


class ChunkScores(BaseModel):
    lecture_structure: LectureStructureScores
    concept_clarity: ConceptClarityScores
    practice_linkage: PracticeLinkageScores
    interaction: InteractionScores


def _collect_score_fields() -> frozenset[str]:
    fields: set[str] = set()
    for sub_model in (
        LectureStructureScores,
        ConceptClarityScores,
        PracticeLinkageScores,
        InteractionScores,
    ):
        fields.update(sub_model.model_fields.keys())
    return frozenset(fields)


SCORE_FIELDS = _collect_score_fields()
_missing_from_scores = VALID_ITEMS - SCORE_FIELDS
_extra_in_scores = SCORE_FIELDS - VALID_ITEMS
if _missing_from_scores or _extra_in_scores:
    raise RuntimeError(
        f"VALID_ITEMS↔Scores 클래스 동기화 실패! "
        f"VALID_ITEMS에만 존재: {_missing_from_scores or '없음'}, "
        f"Scores에만 존재: {_extra_in_scores or '없음'}",
    )

_SCORE_FLOAT = Field(ge=1.0, le=5.0, description="통합 점수 1.0~5.0")
_SCORE_FLOAT_OPTIONAL = Field(None, ge=1.0, le=5.0, description="통합 점수. null 허용")


class SummaryLectureStructureScores(FloatScoreBase):
    learning_objective_intro: Optional[float] = _SCORE_FLOAT_OPTIONAL
    previous_lesson_linkage: Optional[float] = _SCORE_FLOAT_OPTIONAL
    explanation_sequence: float = _SCORE_FLOAT
    key_point_emphasis: float = _SCORE_FLOAT
    closing_summary: Optional[float] = _SCORE_FLOAT_OPTIONAL


class SummaryConceptClarityScores(FloatScoreBase):
    concept_definition: float = _SCORE_FLOAT
    analogy_example_usage: float = _SCORE_FLOAT
    prerequisite_check: float = _SCORE_FLOAT


class SummaryPracticeLinkageScores(FloatScoreBase):
    example_appropriateness: float = _SCORE_FLOAT
    practice_transition: float = _SCORE_FLOAT
    error_handling: float = _SCORE_FLOAT


class SummaryInteractionScores(FloatScoreBase):
    participation_induction: float = _SCORE_FLOAT
    question_response_sufficiency: float = _SCORE_FLOAT


class SummaryScores(BaseModel):
    lecture_structure: SummaryLectureStructureScores
    concept_clarity: SummaryConceptClarityScores
    practice_linkage: SummaryPracticeLinkageScores
    interaction: SummaryInteractionScores


class Evidence(BaseModel):
    item: str = Field(..., description="평가 항목 키 (반드시 영문 소문자 snake_case 사용)")
    quote: str = Field(..., min_length=1, description="원문 발화")
    reason: str = Field(..., min_length=1, description="점수 근거 이유")

    @field_validator("item", mode="before")
    @classmethod
    def validate_item(cls, value: Any) -> str:
        normalized = _normalize_item_key(value)
        if normalized in VALID_ITEMS:
            return normalized
        if normalized in CATEGORY_TO_DEFAULT_ITEM:
            mapped = CATEGORY_TO_DEFAULT_ITEM[normalized]
            _schema_logger.warning(
                "Evidence item '%s'은 카테고리명입니다. '%s'으로 자동 매핑됩니다.",
                value,
                mapped,
            )
            return mapped
        raise ValueError(f"잘못된 evidence 항목: {value} (정규화 시도: {normalized})")


class ChunkResultPayload(BaseModel):
    scores: ChunkScores
    strengths: List[str] = Field(..., description="강점 리스트")
    issues: List[str] = Field(..., description="이슈 리스트")
    evidence: List[Evidence] = Field(..., description="증거 (빈 배열 허용)")


class ItemEvaluation(BaseModel):
    item: str = Field(..., description="항목 ID (snake_case)")
    quote: Optional[str] = Field(None, description="근거 원문 발화 (없으면 null)")
    anchor: str = Field(..., description="대조한 행동 지표 앵커")
    score: Optional[int] = Field(None, ge=1, le=5, description="결정 점수 (null=해당 구간 아님)")

    @field_validator("item", mode="before")
    @classmethod
    def normalize_item(cls, value: Any) -> str:
        normalized = _normalize_item_key(value)
        if normalized in VALID_ITEMS:
            return normalized
        raise ValueError(f"잘못된 CoT 항목: {value}")


EXPECTED_COT_LENGTH = len(VALID_ITEMS)


class LLMInternalResponse(BaseModel):
    cot: List[ItemEvaluation] = Field(..., min_length=EXPECTED_COT_LENGTH, alias="structured_thought_process")
    final_output: ChunkResultPayload = Field(...)

    model_config = {"populate_by_name": True}


class ChunkResult(BaseModel):
    chunk_id: int = Field(..., ge=1)
    start_time: str
    end_time: str
    scores: ChunkScores
    strengths: List[str] = Field(...)
    issues: List[str] = Field(...)
    evidence: List[Evidence]
    status: ChunkStatus = Field(default=ChunkStatus.SUCCESS)
    is_fallback: bool = False
    failure_reason: Optional[str] = None
    failure_class: Optional[FailureClass] = None
    retry_count: int = 0
    elapsed_ms: Optional[int] = Field(None, ge=0)
    token_usage: Optional[TokenUsage] = None
    reliability: Optional[ReliabilityMetrics] = None

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("시간은 HH:MM 형식이어야 합니다.")
        hour_s, minute_s = parts
        if not (hour_s.isdigit() and minute_s.isdigit()):
            raise ValueError("시간은 HH:MM 형식이어야 합니다.")
        hour = int(hour_s)
        minute = int(minute_s)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"시간 범위 초과: {value} (00:00~23:59)")
        return value


class ChunkStateRecord(BaseModel):
    """IRepository.save_chunk_state의 파라미터를 담는 저장 전용 모델."""

    lecture_id: str
    chunk_id: int
    status: str
    result: Optional[ChunkResult] = None
    failure_reason: Optional[str] = None


class ChunkMetadata(BaseModel):
    chunk_id: int = Field(..., ge=1)
    start_time: str
    end_time: str
    text: str
    line_count: int = Field(..., ge=1)
    word_count: int = Field(..., ge=1)
    previous_chunk_tail: Optional[str] = Field(None)
    total_chunks: Optional[int] = Field(None, description="전체 청크 수 (위치 힌트 용)")


class AggregatedAnalysis(BaseModel):
    summary_scores: SummaryScores
    overall_strengths: List[str] = Field(..., description="최종 통합 강점 리스트")
    overall_issues: List[str] = Field(..., description="최종 통합 이슈 리스트")
    overall_evidences: List[Evidence] = Field(..., description="최종 통합 근거 리스트")


class AggregatedResult(BaseModel):
    llm_aggregated_analysis: AggregatedAnalysis
    run_metadata: RunMetadata = Field(default_factory=RunMetadata)


class ScriptLine(BaseModel):
    timestamp: str
    speaker_id: str
    text: str


class ParsedScript(BaseModel):
    lines: List[ScriptLine]
    parse_failure_count: int = 0

    @model_validator(mode="after")
    def ensure_non_empty(self) -> "ParsedScript":
        if not self.lines:
            raise ValueError("파싱된 스크립트에 최소 한 줄이 있어야 합니다.")
        return self


class RefinedList(BaseModel):
    items: List[str] = Field(..., min_length=8, max_length=15, description="동어반복 없이 분할된 최종 문장 리스트")
