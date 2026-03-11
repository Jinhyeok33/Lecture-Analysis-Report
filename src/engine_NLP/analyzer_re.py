# 1. 언어표현품질
# 1.1. 불필요한 반복 - re

# analyzer.py
import json
import os
import argparse
from konlpy.tag import Okt
from collections import Counter


class LanguageQualityAnalyzer:
    def __init__(self):
        self.okt = Okt()
        self.filler_words = ["이제", "그래서", "그러니까", "근데", "그러면", "일단", "약간", "좀", "사실", "뭐", "그", "어", "음", "보시면", "보면", "아무튼", "어쨌든", "그래가지고", "뭐냐면", "뭐랄까"]

    def analyze(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='cp949') as f:
                text = f.read()

        words = self.okt.morphs(text)
        detected_fillers = [word for word in words if word in self.filler_words]
        filler_counts = dict(Counter(detected_fillers))
        
        total_words = len(words)
        repeat_ratio = round(sum(filler_counts.values()) / total_words, 2) if total_words > 0 else 0

        return {
            "lecture_id": os.path.basename(file_path),
            "language_quality": {
                "repeat_expressions": filler_counts,
                "repeat_ratio": repeat_ratio
            }
        }



# --- 터미널 테스트용 코드 ---
if __name__ == "__main__":
    # 터미널 인자 처리 (argparse)
    parser = argparse.ArgumentParser(description="강의 스크립트 불필요 표현 분석기")
    parser.add_argument("file", type=str, help="분석할 파일의 경로")
    
    args = parser.parse_args()

    # 클래스 생성 및 실행
    analyzer = LanguageQualityAnalyzer()
    result = analyzer.analyze(args.file)
    
    # 결과 출력
    print(json.dumps(result, indent=2, ensure_ascii=False))


#터미널 입력
#의존성 (라이브러리) 먼저 설치
# pip install konlpy 
# pip install kss
#파일실행: python (py파일경로) (실행대상파일경로)
# python /workspaces/NLP-internship/src/engine_NLP/analyzer.py /workspaces/NLP-internship/script/raw/2026-02-02_kdt-backendj-21th.txt