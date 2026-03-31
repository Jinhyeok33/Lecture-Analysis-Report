# 1. 언어표현품질 (불필요한 반복, 발화완결성, 언어일관성)

import re
import warnings
from collections import Counter
from kiwipiepy import Kiwi

# 경고 무시 설정
warnings.filterwarnings("ignore")

class LanguageQualityAnalyzer:
    def __init__(self, kiwi=None):
        # 외부에서 넘겨받은 kiwi 사용
        self.kiwi = kiwi
        
        # 1. 불필요한 중복 표현 사전 (Filler Words)
        # 1.1. 부사/접속사형 필러 (문맥에 따라 의미가 있으나 습관적으로 사용됨)
        self.adverb_fillers = {
            "이제", "그래서", "그러니까", "근데", "그러면", "일단", "약간", "좀", 
            "사실", "아무튼", "어쨌든", "그래가지고", "말하자면"
        }

        # 1.2. 감탄사/관형사형 필러 (단어 자체보다 '품사'가 중요)
        self.pure_fillers = {"뭐", "그", "어", "음", "저", "에"}
        
        # 1.3. 동사형 필러의 어간 (보시면 -> 보다, 뭐냐면 -> 뭐이다 등)
        self.verb_filler_lemmas = {"보다", "보시", "뭐이다", "그러다"}

        # 2. 확장된 종결어미 사전 (Kiwi EF 태그 구어체/문어체 완벽 대응)
        self.ENDING_DICT = {
            # --- Formal (격식체/해요체/하십시오체) ---
            # 기본 종결
            "습니다": "formal", "ㅂ니다": "formal", "어요": "formal", "아요": "formal", "여요": "formal",
            "오": "formal", "소": "formal",
            
            # 의문/권유/청유형
            "까요": "formal", "ㄹ까요": "formal", "을까요": "formal", 
            "나요": "formal", "가요": "formal", "은가요": "formal", "는가요": "formal",
            "시죠": "formal", "으시죠": "formal", "ㅂ시다": "formal", "읍시다": "formal",
            
            # 확인/공감/감탄
            "지요": "formal", "죠": "formal",      # ~하죠, ~맞죠
            "네요": "formal", "네요 (감탄)": "formal", 
            "군요": "formal", "는군요": "formal", "로군요": "formal", "료": "formal",
            
            # 의지/약속
            "게요": "formal", "ㄹ게요": "formal", "을게요": "formal",
            
            # 구어체 설명/이유/부가 (가장 많이 누락되는 부분)
            "고요": "formal",      # ~하고요, ~나고요
            "거든요": "formal",    # ~하거든요
            "데요": "formal", "는데요": "formal", "은데요": "formal", "ㄴ데요": "formal", "던데요": "formal",
            
            # 인용/전달
            "대요": "formal", "래요": "formal", "재요": "formal", "냬요": "formal",

            # 명령/부탁
            "세요": "formal", "으세요": "formal", "셔요": "formal", "으셔요": "formal", 
            "십시오": "formal", "으십시오": "formal",

            
            # --- Informal (비격식체/해라체/반말/혼잣말) ---
            # 기본 종결
            "다": "informal", "어": "informal", "아": "informal", "여": "informal", "야": "informal",
            
            # 의문
            "니": "informal", "냐": "informal", "느냐": "informal", "으냐": "informal",
            "까": "informal", "ㄹ까": "informal", "을까": "informal",
            
            # 확인/공감/감탄
            "지": "informal",      # ~하지, ~맞지
            "네": "informal", 
            "군": "informal", "구나": "informal", "는구나": "informal", "로구나": "informal",
            
            # 의지/약속/청유
            "자": "informal", "마": "informal", "음세": "informal",
            
            # 구어체 설명/이유/부가
            "고": "informal",      # ~하고, ~먹고 (문장 끝에 올 때)
            "거든": "informal",
            "는데": "informal", "은데": "informal", "ㄴ데": "informal", "던데": "informal",
            
            # 인용/전달
            "대": "informal", "래": "informal", "재": "informal", "냬": "informal",
            
            # 명령
            "어라": "informal", "아라": "informal", "여라": "informal",
            "렴": "informal", "으렴": "informal", "셔라": "informal", "으셔라": "informal",
        }

    # 💡 메타데이터 제거 메서드
    def _remove_metadata(self, raw_text: str) -> str:
        """STT 텍스트에서 타임스탬프와 화자 ID를 제거합니다."""
        pattern = re.compile(r"<[^>]+>\s+[^\s:]+:\s*")
        cleaned_lines = []
        for line in raw_text.strip().split('\n'):
            if not line.strip():
                continue
            clean_line = pattern.sub("", line).strip()
            cleaned_lines.append(clean_line)
        return "\n".join(cleaned_lines)


    def analyze(self, text: str, file_name: str = "input_text") -> dict:
        """텍스트를 분석하여 언어 품질(중복 표현, 문장 스타일, 완성도) 결과를 반환합니다."""
        
        # 방어 로직: Kiwi가 없으면 자체 생성
        if not self.kiwi:
            self.kiwi = Kiwi()

        if not text or not text.strip():
            return {
                "lecture_id": file_name,
                "error": "분석할 내용이 없습니다."
            }

        # 메타데이터 정제 선적용
        clean_text = self._remove_metadata(text)
        
        # (선택 사항) 정제 후 남은 텍스트가 아예 없을 경우를 대비한 방어 로직
        if not clean_text:
            return {"lecture_id": file_name, "error": "전처리 후 남은 문장이 없습니다."}


        # --- 1. 문장 분리 및 기본 통계 ---
        kiwi_sentences = self.kiwi.split_into_sents(clean_text)
        total_sentences = len(kiwi_sentences) if len(kiwi_sentences) > 0 else 1
        
        # --- 2. 중복 표현(Filler Words) 분석 ---
        tokens = self.kiwi.tokenize(clean_text)
        total_token_count = len(tokens) # 분모로 사용할 전체 단어(토큰) 수
        
        detected_fillers = []
        for t in tokens:
            # A) 감탄사(IC)는 무조건 필러로 인정 (그, 어, 음, 뭐...)
            if t.tag == 'IC':
                detected_fillers.append(t.form)
            
            # B) 관형사(MM)나 부사(MA*) 중 사전에 정의된 습관어
            elif t.tag in ['MM', 'MAG', 'MAJ'] and t.form in self.adverb_fillers:
                detected_fillers.append(t.form)
            
            # C) 동사(VV, VA) 중 '보시면', '보면' 등의 필러성 어구
            # t.lemma(어간)를 사용하여 '보시면', '보시면은', '보면'을 모두 '보다'라는 단어의 원형으로 체크
            elif t.tag.startswith('V') and t.lemma in self.verb_filler_lemmas:
                # 단, '보다'가 진짜 'Watch'의 의미가 아닌 습관적 삽입구인 경우만.
                if t.form in ["보시면", "보면", "보시면은"]:
                    detected_fillers.append(t.form)
            
            # D) '뭐랄까', '뭐냐면' 같은 복합 필러 처리
            elif t.form in ["뭐냐면", "뭐랄까"]:
                detected_fillers.append(t.form)
            
            """
            적용 결과 예시
            이 코드를 적용하면 다음과 같은 문장에서 차이가 발생합니다:
            "사실(NNG, 명사)을 확인하세요" → 수집 안 함 (전문 용어/정보로 간주)
            "사실(MAG, 부사) 제가 말이죠" → 수집함 (필러로 간주)
            "화면을 보시면(VV+어미)" → 수집함 (동사형 필러로 간주)
            """

        filler_counts = dict(Counter(detected_fillers))
        total_filler_count = sum(filler_counts.values())

        repeat_ratio = round(total_filler_count / total_sentences, 4)
        repeat_density = round((total_filler_count / total_token_count), 4) if total_token_count > 0 else 0

        # --- 3. 언어 일관성 및 문장 완성도 분석 ---
        formal_count = 0
        informal_count = 0
        complete_count = 0

        for sent in kiwi_sentences:
            # 형태소 분석 결과를 가져옴
            analysis_result = self.kiwi.analyze(sent.text)[0][0]
            
            # [보완 1] 감탄사/기호만 있는 무의미한 파편("네,", "어,") 필터링
            has_valid_meaning = any(t.tag.startswith('N') or t.tag.startswith('V') for t in analysis_result)
            if not has_valid_meaning:
                # 감탄사나 기호로만 이루어진 조각은 '전체 문장 수'에서 제외하고 건너뜀
                total_sentences -= 1 # 전체 문장 모수에서 제외
                continue

            found_ef = None
            has_yo = "" # 존댓말 보조사 '요'를 임시 저장할 변수

            for token in reversed(analysis_result):
                # [수정 1] Kiwi가 반환하는 특수 종성 자모(ᆸ, ᆯ, ᆫ)를 일반 호환 자모(ㅂ, ㄹ, ㄴ)로 변환
                # (유니코드 \u11b8 = ᆸ, \u11af = ᆯ, \u11ab = ᆫ)
                normalized_form = token.form.replace('\u11b8', 'ㅂ').replace('\u11af', 'ㄹ').replace('\u11ab', 'ㄴ')

                # EF(종결 어미) 태그 발견 시, 뒤에 떨어져 있던 '요'(has_yo)가 있다면 결합
                if token.tag == 'EF': 
                    found_ef = normalized_form + has_yo
                    break

                # 탐색 무시 및 탐색 중단 로직 구현
                # 문장 끝에 붙을 수 있는 마침표(SF), 쉼표(SP), 인용부호(SS)는 패스하고 계속 탐색
                if token.tag in ['SF', 'SP', 'SS']: 
                    continue

                # [수정 4] 구어체 존댓말 보조사(JX) '요'를 정상적으로 캐치하여 임시 저장
                if token.tag == 'JX':
                    if token.form == '요':
                        has_yo = "요"
                    continue

                # [보완 3] 종결어미(EF)뿐만 아니라 연결어미(EC)도 문장 끝에 오면 어미로 인정
                if token.tag == 'EC':
                    found_ef = normalized_form + has_yo
                    break

                # 명사(NNG)나 동사 어간(VV) 등을 만나면 종결어미가 없는 것으로 간주
                break

            # 스타일 판별 및 완성 문장 카운트
            if found_ef in self.ENDING_DICT:
                complete_count += 1
                if self.ENDING_DICT[found_ef] == "formal":
                    formal_count += 1
                else:
                    informal_count += 1
        
        # 최종 지표 계산
        completeness_ratio = complete_count / total_sentences
        formal_ratio = round(formal_count / total_sentences, 3)
        informal_ratio = round(informal_count / total_sentences, 3)

        # --- 4. 결과 통합 ---
        return {
            "lecture_id": file_name,
            "language_quality": {
                "repeat_expressions": filler_counts,
                "total_sentences": total_sentences,
                "total_token_count": total_token_count,
                "total_filler_count": total_filler_count,
                "repeat_ratio": repeat_ratio,
                "repeat_density": repeat_density,
                "incomplete_sentence_ratio": round(1 - completeness_ratio, 3),
                "speech_style_ratio": {
                    "formal": formal_ratio,
                    "informal": informal_ratio
                }
            }
        }