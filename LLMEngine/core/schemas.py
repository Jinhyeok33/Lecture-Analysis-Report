"""LLM 분석 엔진용 Pydantic 스키마."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

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

_SCORE_FLOAT_OPTIONAL = Field(None, ge=1.0, le=5.0, description="통합 점수. null 허용")

class SummaryLectureStructureScores(FloatScoreBase):
    learning_objective_intro: Optional[float] = _SCORE_FLOAT_OPTIONAL
    previous_lesson_linkage: Optional[float] = _SCORE_FLOAT_OPTIONAL
    explanation_sequence: float = Field(ge=1.0, le=5.0)
    key_point_emphasis: float = Field(ge=1.0, le=5.0)
    closing_summary: Optional[float] = _SCORE_FLOAT_OPTIONAL

class SummaryConceptClarityScores(FloatScoreBase):
    concept_definition: float
    analogy_example_usage: float
    prerequisite_check: float

class SummaryPracticeLinkageScores(FloatScoreBase):
    example_appropriateness: float
    practice_transition: float
    error_handling: float

class SummaryInteractionScores(FloatScoreBase):
    participation_induction: float
    question_response_sufficiency: float

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
        if not isinstance(value, str):
            value = str(value)
        normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
        if normalized in VALID_ITEMS:
            return normalized
        if normalized in CATEGORY_TO_DEFAULT_ITEM:
            return CATEGORY_TO_DEFAULT_ITEM[normalized]
        raise ValueError(f"잘못된 evidence 항목: {value} (정규화 시도: {normalized})")

class ChunkResultPayload(BaseModel):
    scores: ChunkScores
    strengths: List[str] = Field(..., description="강점 리스트")
    issues: List[str] = Field(..., description="이슈 리스트")
    evidence: List[Evidence] = Field(..., description="증거 (빈 배열 허용)")

ChunkAnalysisResult = ChunkResultPayload

class ItemEvaluation(BaseModel):
    item_name: str = Field(..., description="평가 항목 (반드시 영문 소문자 snake_case 사용)")
    reasoning: str = Field(..., description="논리 서술")
    identified_quote: Optional[str] = Field(None, description="원문 발화")
    determined_score: Optional[int] = Field(None, description="결정된 점수")

class LLMInternalResponse(BaseModel):
    structured_thought_process: List[ItemEvaluation] = Field(..., min_length=13)
    final_output: ChunkAnalysisResult = Field(...)

class ChunkResult(BaseModel):
    chunk_id: int = Field(..., ge=1)
    start_time: str
    end_time: str
    scores: ChunkScores
    strengths: List[str] = Field(...)
    issues: List[str] = Field(...)
    evidence: List[Evidence]

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("시간은 HH:MM 형식이어야 합니다.")
        hour, minute = parts
        if not (hour.isdigit() and minute.isdigit()):
            raise ValueError("시간은 HH:MM 형식이어야 합니다.")
        return value

class ChunkMetadata(BaseModel):
    chunk_id: int = Field(..., ge=1)
    start_time: str
    end_time: str
    text: str
    line_count: int = Field(..., ge=1)
    word_count: int = Field(..., ge=1)
    previous_chunk_tail: Optional[str] = Field(None)

class AggregatedAnalysis(BaseModel):
    summary_scores: SummaryScores
    overall_strengths: List[str] = Field(..., description="최종 통합 강점 리스트")
    overall_issues: List[str] = Field(..., description="최종 통합 이슈 리스트")
    overall_evidences: List[Evidence] = Field(..., description="최종 통합 근거 리스트")

class AggregatedResult(BaseModel):
    llm_aggregated_analysis: AggregatedAnalysis

class ScriptLine(BaseModel):
    timestamp: str
    speaker_id: str
    text: str

class ParsedScript(BaseModel):
    lines: List[ScriptLine]

    @model_validator(mode="after")
    def ensure_non_empty(self) -> "ParsedScript":
        if not self.lines:
            raise ValueError("파싱된 스크립트에 최소 한 줄이 있어야 합니다.")
        return self

class RefinedList(BaseModel):
    # [수정] 8로 하향 조정하여 10개 목표 달성 실패 시 파이프라인 붕괴 방지
    items: List[str] = Field(..., min_length=8, max_length=15, description="동어반복 없이 분할된 최종 문장 리스트")