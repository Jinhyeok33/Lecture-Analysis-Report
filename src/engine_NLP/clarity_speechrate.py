# 5.1. 발화속도 적절성

import re
import sys
import json
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
                if gap < 60:
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


#의존성
# 없음

#실행 한번에 복붙
# python /workspaces/NLP-internship/src/engine_NLP/clarity_speechrate.py /workspaces/NLP-internship/script/raw/2026-02-02_kdt-backendj-21th.txt


#https://gemini.google.com/app/5c31446b7e9b2d3b?hl=ko