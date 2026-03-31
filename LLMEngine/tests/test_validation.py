"""validation.py 단위 테스트 — evidence 검증, 유사도, 환각 탐지."""

from __future__ import annotations

import pytest

from LLMEngine.core.schemas import Evidence
from LLMEngine.core.exceptions import HallucinationError
from LLMEngine.application.validation import (
    validate_evidence, validate_evidence_quote, normalize_text, _compute_similarity,
)


SAMPLE_CHUNK = (
    "오늘은 입출력 IO 개념을 이해하고 프로그램에서 데이터 흐름을 설명할 수 있는 상태까지 가보겠습니다. "
    "입출력이라는 것은 결국 프로그램하고 외부 자원 사이에서 데이터가 이동하는 과정이라고 보시면 됩니다."
)


class TestNormalizeText:
    def test_strips_whitespace_and_symbols(self):
        assert normalize_text("hello, world!") == "helloworld"

    def test_empty(self):
        assert normalize_text("") == ""

    def test_korean(self):
        result = normalize_text("강의를 시작합니다.")
        assert "강의를시작합니다" == result


class TestComputeSimilarity:
    def test_exact_substring_100(self):
        score = _compute_similarity("데이터가 이동하는 과정", SAMPLE_CHUNK)
        assert score == 100.0

    def test_empty_quote_zero(self):
        score = _compute_similarity("", SAMPLE_CHUNK)
        assert score == 0.0

    def test_irrelevant_low_score(self):
        score = _compute_similarity("완전히 관련 없는 문장입니다 XYZ", SAMPLE_CHUNK)
        assert score < 80


class TestValidateEvidenceQuote:
    def test_matching_quote_passes(self):
        assert validate_evidence_quote("데이터가 이동하는 과정", SAMPLE_CHUNK) is True

    def test_non_matching_quote_fails(self):
        assert validate_evidence_quote("전혀 다른 내용", SAMPLE_CHUNK) is False

    def test_empty_quote_fails(self):
        assert validate_evidence_quote("   ", SAMPLE_CHUNK) is False


class TestValidateEvidence:
    def _make_ev(self, quote: str) -> Evidence:
        return Evidence(item="explanation_sequence", quote=quote, reason="테스트")

    def test_empty_list_returns_zero(self):
        detail = validate_evidence([], SAMPLE_CHUNK)
        assert detail.pass_ratio == 0.0
        assert detail.avg_similarity == 0.0
        assert detail.total_requested == 0

    def test_all_pass(self):
        evs = [self._make_ev("데이터가 이동하는 과정")]
        detail = validate_evidence(evs, SAMPLE_CHUNK)
        assert detail.pass_ratio > 0
        assert detail.total_passed == 1

    def test_hallucination_detected(self):
        fake_quotes = [self._make_ev(f"환각 인용 {i}번") for i in range(3)]
        with pytest.raises(HallucinationError):
            validate_evidence(fake_quotes, SAMPLE_CHUNK)

    def test_mixed_quotes_pass_ratio(self):
        good = self._make_ev("데이터가 이동하는 과정")
        bad = self._make_ev("완전히 거짓 인용")
        evs = [good, bad]
        detail = validate_evidence(evs, SAMPLE_CHUNK, min_pass_ratio=0.3)
        assert 0 < detail.pass_ratio <= 1.0
        assert detail.total_passed >= 1
