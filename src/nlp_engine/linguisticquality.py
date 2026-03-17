# 1. 언어표현품질 (불필요한 반복, 발화완결성, 언어일관성)

import re
import warnings
from collections import Counter
from kiwipiepy import Kiwi

# 경고 무시 설정
warnings.filterwarnings("ignore")

class LanguageQualityAnalyzer:
    def __init__(self, kiwi=None):
        # 외부에서 넘겨받은 kiwi 사용
        self.kiwi = kiwi
        
        # 1. 불필요한 중복 표현 사전 (Filler Words)
        self.filler_words = [
            "이제", "그래서", "그러니까", "근데", "그러면", "일단", "약간", "좀", 
            "사실", "뭐", "그", "어", "음", "보시면", "보면", "아무튼", 
            "어쨌든", "그래가지고", "뭐냐면", "뭐랄까"
        ]
        
        # 2. 간소화된 종결어미 사전 (Kiwi EF 태그 기반)
        self.ENDING_DICT_SIMPLE = {
            # Formal (격식/해요체)
            "습니다": "formal", "ㅂ니다": "formal", "어요": "formal", "아요": "formal", 
            "지요": "formal", "네요": "formal", "가요": "formal", "게요": "formal",
            "나요": "formal", "까요": "formal", "데요": "formal", "료": "formal", 
            "오": "formal", "세요": "formal", "셔요": "formal",

            # Informal (해라/반말/혼잣말)
            "다": "informal", "어": "informal", "아": "informal", "니": "informal", 
            "군": "informal", "구나": "informal", "나": "informal", "자": "informal", 
            "마": "informal", "어라": "informal", "아라": "informal", "지": "informal"
        }

    def analyze(self, text: str, file_name: str = "input_text") -> dict:
        """텍스트를 분석하여 언어 품질(중복 표현, 문장 스타일, 완성도) 결과를 반환합니다."""
        
        # 방어 로직: Kiwi가 없으면 자체 생성
        if not self.kiwi:
            self.kiwi = Kiwi()

        if not text or not text.strip():
            return {
                "lecture_id": file_name,
                "error": "분석할 내용이 없습니다."
            }

        # --- 1. 문장 분리 및 기본 통계 ---
        kiwi_sentences = self.kiwi.split_into_sents(text)
        total_sentences = len(kiwi_sentences) if len(kiwi_sentences) > 0 else 1
        
        # --- 2. 중복 표현(Filler Words) 분석 ---
        tokens = self.kiwi.tokenize(text)
        total_token_count = len(tokens) # 분모로 사용할 전체 단어(토큰) 수
        
        detected_fillers = []
        for t in tokens:
            # 1) 단어가 filler_words에 포함되는지 확인
            if t.form in self.filler_words:
                # 2) '어', '음', '그' 등이 '감탄사(IC)'로 쓰였을 때만 필러로 인정
                if t.tag == 'IC':
                    detected_fillers.append(t.form)
                # 3) '이제', '일단' 등 부사(MA) 성격의 단어는 그대로 카운트
                elif t.tag.startswith('MA'):
                    detected_fillers.append(t.form)

        filler_counts = dict(Counter(detected_fillers))
        total_filler_count = sum(filler_counts.values())

        repeat_ratio = round(total_filler_count / total_sentences, 4)
        repeat_density = round((total_filler_count / total_token_count), 4) if total_token_count > 0 else 0

        # --- 3. 언어 일관성 및 문장 완성도 분석 ---
        formal_count = 0
        informal_count = 0
        complete_count = 0

        for sent in kiwi_sentences:
            # 형태소 분석 결과를 가져옴
            analysis_result = self.kiwi.analyze(sent.text)[0][0]
            
            found_ef = None
            for token in reversed(analysis_result):
                if token.tag == 'EF': # 종결 어미 태그 탐색
                    found_ef = token.form
                    break
                # 의미 없는 기호나 서술격 조사는 건너뜀
                if token.tag in ['VCP', 'VCN', 'SF']: 
                    continue
            
            # 스타일 판별 및 완성 문장 카운트
            if found_ef in self.ENDING_DICT_SIMPLE:
                complete_count += 1
                if self.ENDING_DICT_SIMPLE[found_ef] == "formal":
                    formal_count += 1
                else:
                    informal_count += 1
        
        # 최종 지표 계산
        completeness_ratio = complete_count / total_sentences
        formal_ratio = round(formal_count / total_sentences, 2)
        informal_ratio = round(informal_count / total_sentences, 2)

        # --- 4. 결과 통합 ---
        return {
            "lecture_id": file_name,
            "language_quality": {
                "repeat_expressions": filler_counts,
                "total_sentences": total_sentences,
                "total_filler_count": total_filler_count,
                "repeat_ratio": repeat_ratio,
                "repeat_density": repeat_density,
                "incomplete_sentence_ratio": round(1 - completeness_ratio, 2),
                "speech_style_ratio": {
                    "formal": formal_ratio,
                    "informal": informal_ratio
                }
            }
        }