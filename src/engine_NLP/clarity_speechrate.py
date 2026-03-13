# 3.1. 발화속도 적절성

import re
from datetime import datetime, timedelta

class SpeechRateAnalyzer:
    def __init__(self):
        # 평가 기준 설정
        self.thresholds = [
            (100, "very_low", 3), (130, "low", 4), (160, "optimal", 5),
            (180, "high", 4), (200, "very_high", 3), (float('inf'), "excessive", 2)
        ]

    def _parse_time(self, time_str, last_dt=None):
        fmt = "%H:%M:%S"
        try:
            current_dt = datetime.strptime(time_str, fmt)
            # 12시간제 보정: 이전 시간보다 작아지면 12시간을 더함
            if last_dt and current_dt < last_dt:
                current_dt += timedelta(hours=12)
            return current_dt
        except ValueError:
            return None

    def _analyze_script_with_gaps(self, script_text):
        lines = [l for l in script_text.strip().split('\n') if l.strip()]
        if not lines: return 0, 0

        time_pattern = r"<(.*?)\>"
        total_word_count = 0
        effective_duration_seconds = 0
        
        last_dt = None

        for line in lines:
            time_match = re.search(time_pattern, line)
            if not time_match: continue
            
            current_time_str = time_match.group(1)
            current_dt = self._parse_time(current_time_str, last_dt)
            if not current_dt: continue
            
            # 텍스트 정제 및 단어 수 합산
            content = re.sub(r"<[^>]+>\s+[^\s:]+:\s*", "", line).strip()
            total_word_count += len(content.split())

            # 1분 이상 침묵 제외 로직
            if last_dt is not None:
                gap = (current_dt - last_dt).total_seconds()
                if gap < 20:
                    effective_duration_seconds += gap
            
            last_dt = current_dt

        return total_word_count, effective_duration_seconds

    def get_classification(self, wpm):
        for limit, label, score in self.thresholds:
            if wpm <= limit: return label, score
        return "excessive", 2

    def analyze(self, script_text):
        word_count, effective_sec = self._analyze_script_with_gaps(script_text)
        effective_min = effective_sec / 60
        wpm = round(word_count / effective_min) if effective_min > 0 else 0
        classification, score = self.get_classification(wpm)
        
        return {
            "concept_clarity_metrics": {
                "speech_rate_wpm": wpm,
                "classification": classification,
                "score": score
            },
            "raw_stats": {
                "total_words": word_count,
                "effective_duration_sec": round(effective_sec)
            }
        }