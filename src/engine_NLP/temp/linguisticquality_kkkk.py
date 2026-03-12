import sys
import json
import re
from kiwipiepy import Kiwi

class LanguageQualityAnalyzer:
    def __init__(self):
        # 분석 엔진 초기화 (인스턴스 생성 시 한 번만 실행)
        self.kiwi = Kiwi()
        
        # 간소화된 종결어미 사전 (Kiwi EF 태그 기반)
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

    def analyze(self, text: str) -> dict:
        """텍스트를 분석하여 언어 일관성 및 미완성 문장 비율을 반환합니다."""
        if not text or not text.strip():
            return {
                "incomplete_sentence_ratio": 0.0,
                "speech_style_ratio": {"formal": 0.0, "informal": 0.0}
            }

        # 1. Kiwi를 이용해 문장 분리
        kiwi_sentences = self.kiwi.split_into_sents(text)
        total_sentences = len(kiwi_sentences)
        
        formal_count = 0
        informal_count = 0
        complete_count = 0

        for sent in kiwi_sentences:
            # 2. 형태소 분석 및 종결 어미(EF) 추출
            tokens = self.kiwi.analyze(sent.text)[0][0]
            
            found_ef = None
            for token in reversed(tokens):
                if token.tag == 'EF':
                    found_ef = token.form
                    break
                # 서술격 조사 등은 건너뛰고 실제 어미 탐색
                if token.tag in ['VCP', 'VCN', 'SF']: 
                    continue
            
            # 3. 스타일 판별
            if found_ef in self.ENDING_DICT_SIMPLE:
                complete_count += 1
                if self.ENDING_DICT_SIMPLE[found_ef] == "formal":
                    formal_count += 1
                else:
                    informal_count += 1
        
        # 4. 결과 지표 계산
        completeness_ratio = complete_count / total_sentences if total_sentences > 0 else 0
        
        return {
            "incomplete_sentence_ratio": round(1 - completeness_ratio, 2),
            "speech_style_ratio": {
                "formal": round(formal_count / total_sentences, 2) if total_sentences > 0 else 0,
                "informal": round(informal_count / total_sentences, 2) if total_sentences > 0 else 0
            }
        }

# --- 터미널 실행을 위한 메인 코드 ---
if __name__ == "__main__":
    # 클래스 인스턴스 생성
    analyzer = LanguageQualityAnalyzer()
    
    # 1. 명령행 인자로 파일 경로를 받았을 경우
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                input_text = f.read()
            print(f"--- '{file_path}' 파일을 분석합니다 ---")
        except Exception as e:
            print(f"파일을 읽는 중 오류 발생: {e}")
            sys.exit(1)
    else:
        # 2. 인자가 없을 경우 기본 예시 데이터 사용
        print("--- 입력 인자가 없어 예시 스크립트를 분석합니다 ---")
        input_text = """
<09:11:17> b54f46b0: 여러분 오늘 수업 진행하도록 하겠습니다.
<09:11:45> b54f46b0: 저희가 오늘 이제 수업할 내용은 자바 아이오 패키지입니다.
<09:11:57> b54f46b0: 지금 다양한 섹션으로 구현할 수가 있는데 여기 보세요.
<12:59:50> b54f46b0: 오전 수업은 여기까지 하고 식사하고 오세요.
<02:00:10> b54f46b0: 자, 오후 수업 시작해 보겠습니다.
        """

    # 분석 실행 및 결과 출력
    analysis_result = analyzer.analyze(input_text)
    print(json.dumps(analysis_result, indent=2, ensure_ascii=False))