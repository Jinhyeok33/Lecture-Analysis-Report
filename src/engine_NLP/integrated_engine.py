import os
import json
from datetime import datetime
from kiwipiepy import Kiwi

# 복구된 3개의 모듈 임포트
from .clarity_speechrate import SpeechRateAnalyzer
from .interactionanalyze import InteractionAnalyzer
from .linguisticquality import LanguageQualityAnalyzer

class IntegratedNLPEngine:
    def __init__(self, output_dir=None):
        # 1. 공통 Kiwi 인스턴스 1번만 생성
        self.kiwi = Kiwi()
        
        # 2. 각 분석기에 Kiwi 주입
        self.speech_analyzer = SpeechRateAnalyzer()
        self.interaction_analyzer = InteractionAnalyzer(kiwi=self.kiwi)
        self.quality_analyzer = LanguageQualityAnalyzer(kiwi=self.kiwi)

        # 3. 저장 폴더 설정
        self.output_dir = output_dir or r"C:\Repositories\NLP-internship\script\output_NLP"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

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

        # 각 모듈 분석 실행
        speech_data = self.speech_analyzer.analyze(script_text)
        interaction_data = self.interaction_analyzer.analyze(script_text)
        quality_data = self.quality_analyzer.analyze(script_text, file_name=file_name)

        # 최종 리포트 조립
        report = {
            "report_info": {
                "source_file": file_name,
                "analysis_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "metrics": {
                "speech_rate": speech_data.get("concept_clarity_metrics", {}),
                "interaction": interaction_data.get("interaction_metrics", {}),
                "linguistic_quality": quality_data.get("language_quality", {})
            }
        }

        # JSON 자동 저장
        self._save_to_json(report, file_name)
        return report

    def _save_to_json(self, data, original_filename):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"analysis_{os.path.splitext(original_filename)[0]}_{timestamp}.json"
        save_path = os.path.join(self.output_dir, output_filename)
        
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)