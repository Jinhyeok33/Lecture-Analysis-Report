import re
from datetime import datetime, timedelta
from kiwipiepy import Kiwi

class InteractionAnalyzer:
    def __init__(self, kiwi=None, min_threshold=3):
        # 외부에서 넘겨받은 kiwi 사용
        self.kiwi = kiwi
        self.min_threshold = min_threshold
        # 핵심 어근 세트 (형태소 분석기의 token.form 형태에 맞추어 하나에 담는 방식에서 품사별로)
        # 💡 개선점 1: 품사(POS)별로 타겟 어간을 분리하여 정확도 향상
        # 명사형 (NNG, NNP 등)
        self.target_nouns = {"이해", "확인", "질문"}
        # 동사/형용사 어간 (VV, VA 등)
        self.target_predicates = {"알", "어렵", "맞", "틀리", "넘어가", "따라오", "괜찮", "궁금하", "보이", "들리"}
        # 의문형 어미 확장
        self.question_endings = {"나요", "가요", "어요", "죠", "까", "까요", "시죠"}

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
        """Kiwi 품사 태깅을 활용한 정밀한 이해 확인 질문 탐지"""
        if not self.kiwi: return False
        
        tokens = self.kiwi.tokenize(text)
        has_target_meaning = False
        is_question_form = False
        
        # '감이 오다' 같은 연어(Collocation) 처리를 위한 상태 변수
        has_gam = False 
        
        for token in tokens:
            form = token.form
            tag = token.tag
            
            # 💡 개선점 2: 품사 태그(tag)를 확인하여 동음이의어 필터링
            # (예: 먹는 '알(Noun)'과 아는 '알(Verb)' 구분)
            
            if tag.startswith('N'): # 명사인 경우
                if form in self.target_nouns:
                    has_target_meaning = True
                elif form == "감":
                    has_gam = True # '감'이 등장했음을 기록
                    
            elif tag.startswith('V'): # 동사/형용사인 경우
                if form in self.target_predicates:
                    has_target_meaning = True
                # 앞에 '감'이 나왔고, 현재 동사가 '오'인 경우 -> "감이 오다"
                elif has_gam and form == "오": 
                    has_target_meaning = True

            # 💡 개선점 3: 종결어미(EF) 및 기호(SF) 매칭 로직 강화
            if tag in {"EF", "SF"}:
                if "?" in form or any(form.endswith(ending) for ending in self.question_endings):
                    is_question_form = True
                
        return has_target_meaning and is_question_form

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