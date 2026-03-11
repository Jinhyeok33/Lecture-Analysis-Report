# 1. 언어표현품질
# 1.1. 불필요한 반복 - kss (코드스페이스에서 시간 너무 오래 걸림)

import json
import os
import argparse
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
        # 절대 경로로 명확히 지정
        self.output_dir = os.path.abspath("/workspaces/NLP-internship/script/output_NLP")
        
        # 폴더가 없으면 생성하고, 생성 여부를 확인
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
            print(f"[시스템] 저장 폴더를 생성했습니다: {self.output_dir}")

    def analyze(self, file_path):
        # 입력 파일 존재 확인
        abs_input_path = os.path.abspath(file_path)
        if not os.path.exists(abs_input_path):
            return {"error": f"입력 파일을 찾을 수 없습니다: {abs_input_path}"}, None

        try:
            with open(abs_input_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(abs_input_path, 'r', encoding='cp949') as f:
                text = f.read()

        # 1. KSS 문장 분리
        sentences = kss.split_sentences(text)
        total_sentences = len(sentences) if len(sentences) > 0 else 1

        # 2. 형태소 분석 및 빈도 체크
        words = self.okt.morphs(text)
        detected_fillers = [word for word in words if word in self.filler_words]
        filler_counts = dict(Counter(detected_fillers))
        total_filler_count = sum(filler_counts.values())

        # 3. 결과 조립
        repeat_ratio = round(total_filler_count / total_sentences, 2)
        result = {
            "lecture_id": os.path.basename(file_path),
            "language_quality": {
                "repeat_expressions": filler_counts,
                "total_sentences": total_sentences,
                "total_filler_count": total_filler_count,
                "repeat_ratio": repeat_ratio
            }
        }

        # 4. JSON 저장 (파일명에서 확장자 제거 후 _analysis.json 붙임)
        base_name = os.path.basename(file_path)
        file_name_only = os.path.splitext(base_name)[0]
        output_filename = f"{file_name_only}_analysis.json"
        output_path = os.path.join(self.output_dir, output_filename)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[오류] 파일 저장 중 문제가 발생했습니다: {e}")
            return result, None

        return result, output_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=str)
    args = parser.parse_args()

    analyzer = LanguageQualityAnalyzer()
    result, saved_path = analyzer.analyze(args.file)
    
    if saved_path:
        print("\n" + "="*50)
        print(f"✅ 분석 완료!")
        print(f"📂 저장 경로: {saved_path}")
        print("="*50)
        # 터미널에서도 결과를 바로 볼 수 있게 출력
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"❌ 실패: {result.get('error')}")


# 의존성
# pip install kss

# 라이브러리 버전확인
# pip show kss

# 실행
# python /workspaces/NLP-internship/src/engine_NLP/analyzer_kss.py /workspaces/NLP-internship/script/raw/2026-02-02_kdt-backendj-21th.txt