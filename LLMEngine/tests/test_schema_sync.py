"""프롬프트↔스키마 동기화 안전장치 테스트.

VALID_ITEMS와 ChunkScores 하위 필드, CATEGORY_TO_DEFAULT_ITEM,
NA_CAPABLE_ITEMS 사이의 정합성을 검증한다.
import 시점 RuntimeError는 schemas.py 로드 자체에서 발생하므로,
여기서는 보조 제약(서브셋 관계 등)을 추가로 검증한다.
"""

from __future__ import annotations

from LLMEngine.core.schemas import (
    VALID_ITEMS, SCORE_FIELDS, CATEGORY_TO_DEFAULT_ITEM, NA_CAPABLE_ITEMS,
    ChunkScores, LectureStructureScores, ConceptClarityScores,
    PracticeLinkageScores, InteractionScores,
)


class TestPromptSchemaSync:
    def test_valid_items_equals_score_fields(self):
        assert VALID_ITEMS == SCORE_FIELDS

    def test_category_defaults_in_valid_items(self):
        for cat, default_item in CATEGORY_TO_DEFAULT_ITEM.items():
            assert default_item in VALID_ITEMS, (
                f"CATEGORY_TO_DEFAULT_ITEM['{cat}'] = '{default_item}' 가 VALID_ITEMS에 없음"
            )

    def test_na_capable_items_subset(self):
        assert NA_CAPABLE_ITEMS <= VALID_ITEMS, (
            f"NA_CAPABLE_ITEMS에 VALID_ITEMS에 없는 항목 존재: {NA_CAPABLE_ITEMS - VALID_ITEMS}"
        )

    def test_chunk_scores_categories_match(self):
        expected_categories = set(CATEGORY_TO_DEFAULT_ITEM.keys())
        actual_categories = set(ChunkScores.model_fields.keys())
        assert expected_categories == actual_categories, (
            f"CATEGORY_TO_DEFAULT_ITEM 키와 ChunkScores 필드 불일치: "
            f"기대={expected_categories}, 실제={actual_categories}"
        )

    def test_item_count_matches_13(self):
        assert len(VALID_ITEMS) == 13

    def test_no_duplicate_fields_across_categories(self):
        all_fields: list[str] = []
        for sub_model in (
            LectureStructureScores, ConceptClarityScores,
            PracticeLinkageScores, InteractionScores,
        ):
            all_fields.extend(sub_model.model_fields.keys())
        assert len(all_fields) == len(set(all_fields)), "Score 클래스 간 필드명 중복"
