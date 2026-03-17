import os
import json
from datetime import datetime
from kiwipiepy import Kiwi

# 공통 설정 파일(/workspaces/NLP-internship/src/config.py)에서 경로 가져오기
from config import OUTPUT_NLP_DIR

# 복구된 3개의 모듈 임포트
from .clarity_speechrate import SpeechRateAnalyzer
from .interactionanalyze import InteractionAnalyzer
from .linguisticquality import LanguageQualityAnalyzer

class IntegratedNLPEngine:
    def __init__(self, output_dir=OUTPUT_NLP_DIR):
        # 1. 공통 Kiwi 인스턴스 1번만 생성
        self.kiwi = Kiwi()
        
        # 2. 각 분석기에 Kiwi 주입
        self.speech_analyzer = SpeechRateAnalyzer()
        self.interaction_analyzer = InteractionAnalyzer(kiwi=self.kiwi)
        self.quality_analyzer = LanguageQualityAnalyzer(kiwi=self.kiwi)

        # 3. 저장 폴더 설정
        self.output_dir = output_dir
        #output_dir or r"C:\Repositories\NLP-internship\script\output_NLP"
        #if not os.path.exists(self.output_dir):
        #    os.makedirs(self.output_dir)

    def _read_file(self, file_path):
        for encoding in ['utf-8', 'cp949']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    return f.read()
            except: continue
        raise Exception(f"파일 읽기 실패 (인코딩 문제일 수 있습니다): {file_path}")

    def analyze_all(self, file_path: str) -> dict:
        script_text = self._read_file(file_path)
        file_name = os.path.basename(file_path)
        
        # 확장자(.txt)를 제외한 순수 파일명만 추출하여 lecture_id로 사용
        lecture_id = os.path.splitext(file_name)[0]

        # 각 모듈 분석 실행
        speech_data = self.speech_analyzer.analyze(script_text)
        interaction_data = self.interaction_analyzer.analyze(script_text)
        quality_data = self.quality_analyzer.analyze(script_text, file_name=lecture_id)

        # --- 사용자 요청에 맞춘 플랫(Flat)한 JSON 구조 조립 ---
        report = {
            "lecture_id": lecture_id,
            "language_quality": quality_data.get("language_quality", {}),
            "concept_clarity_metrics": speech_data.get("concept_clarity_metrics", {}),
            "interaction_metrics": interaction_data.get("interaction_metrics", {})
        }

        # JSON 자동 저장
        self._save_to_json(report, lecture_id)
        return report

    def _save_to_json(self, data, lecture_id):
        # 저장 파일명: analysis_파일명_시간.json 형태 유지
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"analysis_{lecture_id}_{timestamp}.json"
        save_path = os.path.join(self.output_dir, output_filename)
        
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)