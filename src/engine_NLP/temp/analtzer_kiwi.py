import json
import os
import argparse
import warnings
from collections import Counter
from kiwipiepy import Kiwi

# 경고 무시 설정
warnings.filterwarnings("ignore")

class LanguageQualityAnalyzer:
    def __init__(self):
        # Kiwi 초기화 (준비 시간이 매우 짧습니다)
        self.kiwi = Kiwi()
        self.filler_words = [
            "이제", "그래서", "그러니까", "근데", "그러면", "일단", "약간", "좀", 
            "사실", "뭐", "그", "어", "음", "보시면", "보면", "아무튼", 
            "어쨌든", "그래가지고", "뭐냐면", "뭐랄까"
        ]

    def analyze(self, file_path):
        abs_input_path = os.path.abspath(file_path)
        if not os.path.exists(abs_input_path):
            return {"error": f"파일을 찾을 수 없습니다: {abs_input_path}"}

        try:
            with open(abs_input_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(abs_input_path, 'r', encoding='cp949') as f:
                text = f.read()

        # 1. Kiwi를 사용한 문장 분리 (매우 빠름)
        # split_into_sents는 문맥을 파악하여 정확하게 문장을 나눕니다.
        sentences = self.kiwi.split_into_sents(text)
        total_sentences = len(sentences) if len(sentences) > 0 else 1

        # 2. 형태소 분석 및 불필요 표현 빈도 체크
        # tokenize는 텍스트를 형태소 단위로 분리합니다.
        tokens = self.kiwi.tokenize(text)
        
        # 형태소의 '형태(form)'값만 추출하여 리스트 생성
        detected_fillers = [t.form for t in tokens if t.form in self.filler_words]
        filler_counts = dict(Counter(detected_fillers))
        total_filler_count = sum(filler_counts.values())

        # 3. 결과 데이터 조립
        repeat_ratio = round(total_filler_count / total_sentences, 2)
        
        return {
            "lecture_id": os.path.basename(file_path),
            "language_quality": {
                "repeat_expressions": filler_counts,
                "total_sentences": total_sentences,
                "total_filler_count": total_filler_count,
                "repeat_ratio": repeat_ratio
            }
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=str)
    args = parser.parse_args()

    analyzer = LanguageQualityAnalyzer()
    result = analyzer.analyze(args.file)
    print(json.dumps(result, indent=2, ensure_ascii=False))