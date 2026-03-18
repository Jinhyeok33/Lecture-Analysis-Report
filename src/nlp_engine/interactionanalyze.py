import re
from datetime import datetime, timedelta
from kiwipiepy import Kiwi

class InteractionAnalyzer:
    def __init__(self, kiwi=None, min_threshold=3):
        # 외부에서 넘겨받은 kiwi 사용
        self.kiwi = kiwi
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
        # 방어 로직
        if not self.kiwi: return False
        
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
        # 방어 로직: Kiwi가 없으면 자체 생성
        if not self.kiwi:
            self.kiwi = Kiwi()

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
        
        return {
            "interaction_metrics": {
                "understanding_question_count": total_questions,
            #    "effective_duration_hours": round(effective_duration_hours, 3), # 유효 시간 표기
            #    "questions_per_hour": round(total_questions / effective_duration_hours, 2),
            #    "is_sufficient": (total_questions / effective_duration_hours) >= self.min_threshold
            },
            #"distribution": distribution
        }