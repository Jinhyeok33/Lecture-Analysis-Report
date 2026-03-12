import re
import json
import sys
from datetime import datetime, timedelta
from kiwipiepy import Kiwi

class InteractionAnalyzer:
    def __init__(self, min_threshold=3):
        self.kiwi = Kiwi()
        self.min_threshold = min_threshold
        # 확장된 핵심 어근 세트
        self.target_roots = {
            "알다", "이해", "확인", "질문", "되다",
            "어렵다", "하다", "맞다", "틀리다",
            "넘어가다", "따라오다", "괜찮다", "궁금하다", "보이다", "들리다"
        }

    def _parse_time(self, time_str, last_dt=None):
        """12시간제 보정 로직을 포함한 시간 문자열 파싱 함수"""
        fmt = "%H:%M:%S"
        try:
            current_dt = datetime.strptime(time_str, fmt)
            # 12시간제 보정: 이전 시간보다 작아지면 12시간을 더함
            if last_dt and current_dt < last_dt:
                current_dt += timedelta(hours=12)
            return current_dt
        except ValueError:
            return None

    def _is_understanding_question(self, text):
        """Kiwi를 사용하여 의문형 어미와 핵심 키워드 조합 분석"""
        tokens = self.kiwi.tokenize(text)
        has_target_root = False
        is_question_form = False
        
        for token in tokens:
            if token.form in self.target_roots:
                has_target_root = True
            if token.tag in {"EF", "SF"} and ("?" in token.form or token.form in ["나요", "가요", "어요", "죠"]):
                is_question_form = True
                
        return has_target_root and is_question_form

    def analyze(self, script_text):
        lines = [l for l in script_text.strip().split('\n') if l.strip()]
        if not lines:
            return {"error": "분석할 데이터가 없습니다."}
            
        time_pattern = r"<(.*?)\>"
        effective_duration_seconds = 0
        last_dt = None
        
        # 상호작용이 발생한 시점의 '누적 유효 시간'을 저장
        interactions_effective_times = []

        for line in lines:
            time_match = re.search(time_pattern, line)
            if not time_match: continue
            
            current_time_str = time_match.group(1)
            current_dt = self._parse_time(current_time_str, last_dt)
            if not current_dt: continue
            
            # 유효 강의시간 누적 (제공해주신 20초 미만 간격 합산 로직)
            if last_dt is not None:
                gap = (current_dt - last_dt).total_seconds()
                if gap < 20:
                    effective_duration_seconds += gap
            
            last_dt = current_dt

            # 텍스트 정제 (타임스탬프 및 화자 ID 제거)
            content = re.sub(r"<[^>]+>\s+[^\s:]+:\s*", "", line).strip()

            # 질문 탐지 시, 현재까지 누적된 유효 시간을 기록
            if self._is_understanding_question(content):
                interactions_effective_times.append(effective_duration_seconds)

        # 시간 계산 및 0 나누기 방지
        effective_duration_hours = max(effective_duration_seconds / 3600, 0.001)
        total_questions = len(interactions_effective_times)
        
        # 분포도 계산 (절대 시간이 아닌 '유효 강의 시간'을 기준으로 3등분)
        #distribution = {"early": 0, "mid": 0, "late": 0}
        #total_duration = effective_duration_seconds if effective_duration_seconds > 0 else 1
        
        #for effective_time in interactions_effective_times:
        #    pos = effective_time / total_duration
        #    if pos <= 0.33: distribution["early"] += 1
        #    elif pos <= 0.66: distribution["mid"] += 1
        #    else: distribution["late"] += 1

        return {
            "interaction_metrics": {
                "understanding_question_count": total_questions,
            #    "effective_duration_hours": round(effective_duration_hours, 3), # 유효 시간 표기
            #    "questions_per_hour": round(total_questions / effective_duration_hours, 2),
            #    "is_sufficient": (total_questions / effective_duration_hours) >= self.min_threshold
            },
            #"distribution": distribution
        }

# --- 터미널 실행을 위한 메인 코드 ---
if __name__ == "__main__":
    analyzer = InteractionAnalyzer()
    
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
        # 2. 인자가 없을 경우 기본 예시 데이터 사용 (12시간제 전환 및 갭 테스트용)
        print("--- 입력 인자가 없어 예시 스크립트를 분석합니다 ---")
        input_text = """
<11:59:45> b54f46b0: 여러분 오늘 수업 진행하도록 하겠습니다. 알겠죠?
<11:59:55> b54f46b0: 10초 지났습니다. 다들 이해하셨나요?
<12:00:10> b54f46b0: 쉬는 시간 가지겠습니다.
<01:00:10> b54f46b0: 자, 오후 수업 시작해 보겠습니다. 다들 들리시죠?
<01:00:20> b54f46b0: 이 부분 코드가 좀 복잡한데 되셨어요?
        """

    # 분석 실행 및 결과 출력
    analysis_result = analyzer.analyze(input_text)
    print(json.dumps(analysis_result, indent=2, ensure_ascii=False))