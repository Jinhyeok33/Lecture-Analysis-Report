from kiwipiepy import Kiwi
import json
import re

# 종결어미 사전
ENDING_DICT = {
    # Formal (존댓말)
    "습니다": "formal", "입니다": "formal", "합니다": "formal", "됩니다": "formal", "있습니다": "formal",
    "해요": "formal", "이에요": "formal", "예요": "formal", "있어요": "formal", "돼요": "formal",
    "네요": "formal", "고요": "formal", "거든요": "formal", "죠": "formal", "세요": "formal",
    "까요": "formal", "나요": "formal", "게요": "formal", "에요": "formal", "습니까": "formal", 
    "입니까": "formal", "합니까": "formal", "드려요": "formal", "바랍니다": "formal",
    
    # Informal (반말)
    "다": "informal", "이다": "informal", "한다": "informal", "된다": "informal", "있다": "informal",
    "어": "informal", "아": "informal", "야": "informal", "지": "informal", "네": "informal",
    "니": "informal", "냐": "informal", "대": "informal", "래": "informal", "자": "informal",
    "군": "informal", "구나": "informal", "어라": "informal", "잖아": "informal"
}

# 분석 엔진 초기화 시 Kiwi 인스턴스 생성 (전역으로 한 번만 생성하는 것이 효율적)
kiwi = Kiwi()



def analyze_speech_quality(text: str) -> str:
    if not text or not text.strip():
         return json.dumps({
            "incomplete_sentence_ratio": 0.0,
            "speech_style_ratio": {"formal": 0.0, "informal": 0.0}
        }, indent=2)

    # 1. Kiwi를 이용해 문장 분리
    # kiwi.split_into_sents는 Sentence 객체를 반환하므로, .text로 문자열만 추출합니다.
    kiwi_sentences = kiwi.split_into_sents(text)
    sentences = [sent.text for sent in kiwi_sentences]
    total_sentences = len(sentences)
    
    if total_sentences == 0:
        return json.dumps({
            "incomplete_sentence_ratio": 0.0,
            "speech_style_ratio": {"formal": 0.0, "informal": 0.0}
        }, indent=2)
        
    complete_count = 0
    formal_count = 0
    informal_count = 0
    
    # 가장 긴 어미부터 매칭되도록 길이 기준 내림차순 정렬
    sorted_endings = sorted(ENDING_DICT.keys(), key=len, reverse=True)
    
    for sent in sentences:
        # 문장 끝의 마침표, 물음표 등 기호와 공백 제거
        clean_sent = re.sub(r'[^가-힣a-zA-Z0-9]$', '', sent.strip())
        
        matched_style = None
        for ending in sorted_endings:
            if clean_sent.endswith(ending):
                matched_style = ENDING_DICT[ending]
                complete_count += 1
                break
                
        if matched_style == "formal":
            formal_count += 1
        elif matched_style == "informal":
            informal_count += 1
            
    # 비율 계산 로직 (소수점 둘째 자리까지 반올림)
    completeness_ratio = complete_count / total_sentences
    incomplete_ratio = round(1 - completeness_ratio, 2)
    
    formal_ratio = round(formal_count / total_sentences, 2)
    informal_ratio = round(informal_count / total_sentences, 2)
    
    result = {
        "incomplete_sentence_ratio": incomplete_ratio,
        "speech_style_ratio": {
            "formal": formal_ratio,
            "informal": informal_ratio
        }
    }
    
    return json.dumps(result, ensure_ascii=False, indent=2)

# ====== 테스트 실행 예시 ======
if __name__ == "__main__":
    sample_text = """
    여러분 오늘 수업 진행하도록 하겠습니다 
    크루드 방법을 학습 이해를 하고 그다음에 데이터 흐름 읽기 쓰기를 구현하는 날이에요
    오늘 이런 것들을 조금 살펴보고
    오후에는 데이터베이스 설치하고 마무리할게요
    이거는 뭐가 좋다
    """
    
    print(analyze_speech_quality(sample_text))



# --- 터미널 실행을 위한 메인 코드 ---
if __name__ == "__main__":
    analyzer = SpeechRateAnalyzer()
    
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
