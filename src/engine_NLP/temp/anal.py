# 1. 언어표현품질
# 1.1. 불필요한 반복 - 

import json
import os
import argparse
import logging
import warnings

# 경고 무시 설정
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings("ignore")

import kss
from konlpy.tag import Okt
from collections import Counter

class LanguageQualityAnalyzer:
    def __init__(self):
        self.okt = Okt()
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

        # 1. KSS 문장 분리 최적화 (텍스트가 길면 잘라서 처리)
        # 235KB 대응: 10,000자 단위로 끊어서 문장 분리 수행
        chunk_size = 10000
        sentences = []
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            sentences.extend(kss.split_sentences(chunk))
        
        total_sentences = len(sentences) if len(sentences) > 0 else 1

        # 2. 형태소 분석 및 빈도 체크
        words = self.okt.morphs(text)
        detected_fillers = [word for word in words if word in self.filler_words]
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



# python /workspaces/NLP-internship/src/engine_NLP/anal.py /workspaces/NLP-internship/script/raw/2026-02-02_kdt-backendj-21th.txt