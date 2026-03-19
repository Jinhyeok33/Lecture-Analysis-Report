import json
from pathlib import Path

from kiwipiepy import Kiwi

from src.common.naming import lecture_id_from_transcript_path, nlp_json_path
from .config import OUTPUT_NLP_DIR
from .clarity_speechrate import SpeechRateAnalyzer
from .interactionanalyze import InteractionAnalyzer
from .linguisticquality import LanguageQualityAnalyzer


class IntegratedNLPEngine:
    def __init__(self, output_dir: str = OUTPUT_NLP_DIR):
        self.kiwi = Kiwi()
        self.speech_analyzer = SpeechRateAnalyzer()
        self.interaction_analyzer = InteractionAnalyzer(kiwi=self.kiwi)
        self.quality_analyzer = LanguageQualityAnalyzer(kiwi=self.kiwi)
        self.output_dir = output_dir
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def _read_file(self, file_path: str) -> str:
        for encoding in ["utf-8", "cp949"]:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    return f.read()
            except Exception:
                continue
        raise Exception(f"파일 읽기 실패 (인코딩 문제일 수 있습니다): {file_path}")

    def analyze_all(self, file_path: str) -> dict:
        lecture_id = lecture_id_from_transcript_path(file_path)
        output_path = nlp_json_path(self.output_dir, lecture_id)

        if output_path.exists():
            with output_path.open("r", encoding="utf-8-sig") as f:
                return json.load(f)

        script_text = self._read_file(file_path)

        speech_data = self.speech_analyzer.analyze(script_text)
        interaction_data = self.interaction_analyzer.analyze(script_text)
        quality_data = self.quality_analyzer.analyze(script_text, file_name=lecture_id)

        report = {
            "lecture_id": lecture_id,
            "language_quality": quality_data.get("language_quality", {}),
            "concept_clarity_metrics": speech_data.get("concept_clarity_metrics", {}),
            "interaction_metrics": interaction_data.get("interaction_metrics", {}),
        }

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return report
