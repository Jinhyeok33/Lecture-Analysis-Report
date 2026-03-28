import os
import glob
import re
import json
import pandas as pd  # 메타데이터 CSV 로드를 위해 추가
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate

# ==========================================
# 1. 단어 사전 생성 클래스
# ==========================================

class DictionaryGenerator:
    def __init__(self, raw_folder_path, metadata_path, llm_model="gpt-4o"):
        self.raw_folder_path = raw_folder_path
        self.metadata_path = metadata_path  # 메타데이터 파일 경로 추가
        
        # JSON 모드 강제 활성화
        self.llm = ChatOpenAI(
            model=llm_model, 
            temperature=0,
            model_kwargs={"response_format": {"type": "json_object"}}
        )
        self.meta_pattern = re.compile(r'^<\d{2}:\d{2}:\d{2}>\s+[a-zA-Z0-9]+:\s*')
        
    def _get_session_topics(self, file_list):
        """파일명(date_course_id.txt)을 파싱하여 CSV에서 주제와 내용을 추출합니다."""
        print(f"\n[메타데이터 로드] '{self.metadata_path}'에서 강의 정보를 가져옵니다...")
        try:
            # CSV 로드 (인코딩 에러 방지를 위해 utf-8-sig 사용)
            df = pd.read_csv(self.metadata_path, encoding='utf-8-sig')
        except Exception as e:
            print(f"메타데이터 로드 실패 (파일 경로 또는 인코딩을 확인하세요): {e}")
            return "강의 정보 없음"

        topics_set = set()
        
        for file_path in file_list:
            filename = os.path.basename(file_path).replace('.txt', '')
            # 예: 2026-02-02_kdt-backendj-21th -> ['2026-02-02', 'kdt-backendj-21th']
            parts = filename.split('_')
            
            if len(parts) >= 2:
                date_str = parts[0]
                course_id = parts[1]
                
                # DataFrame에서 조건에 맞는 행 필터링
                matched = df[(df['date'] == date_str) & (df['course_id'] == course_id)]
                
                for _, row in matched.iterrows():
                    subject = str(row['subject']).strip()
                    content = str(row['content']).strip()
                    # 예: [객체지향 프로그래밍] 데코레이터 패턴, 옵저버 패턴
                    topics_set.add(f"- [{subject}] {content}")
                    
        if topics_set:
            session_topics = "\n".join(sorted(list(topics_set)))
            print(f"-> 추출된 강의 주제:\n{session_topics}")
            return session_topics
        
        return "강의 정보 없음"

    def _load_and_clean_scripts(self):
        print(f"[{self.raw_folder_path}] 폴더에서 스크립트 로드 중...")
        file_list = glob.glob(os.path.join(self.raw_folder_path, "*.txt"))
        all_sentences = []
        
        for file_path in file_list:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    clean_text = self.meta_pattern.sub('', line)
                    if clean_text:
                        all_sentences.append(clean_text)
                        
        return file_list, all_sentences  # file_list도 함께 반환

    def _extract_jargon_candidates(self, scripts):
        print("\n[단어 추출] 룰베이스 어절 추출 및 조사 제거를 시작합니다...")
        word_freq = {}
        
        for text in scripts:
            clean_text = re.sub(r'[^a-zA-Z가-힣0-9\s]', ' ', text)
            words = clean_text.split()
            
            for w in words:
                w = re.sub(r'(은|는|이|가|을|를|에|에서|로|으로|부터|까지|도|만|의|입니다|합니다|습니다|다|고|며|면)$', '', w)
                w = re.sub(r'(은|는|이|가|을|를|로|으로)$', '', w)
                
                if len(w) < 2 and not re.search(r'[a-zA-Z]', w):
                    continue
                if w.isdigit():
                    continue
                    
                word_freq[w] = word_freq.get(w, 0) + 1

        stop_words = {
            "진행", "수업", "오늘", "내용", "시간", "결과", "설명", "부분", "이해", "사용", 
            "문제", "확인", "저장", "처리", "출력", "입력", "개수", "가이드", "강사", "개념", 
            "개별", "객체", "검색", "데이터", "파일", "작업", "해주", "하시", "이것", "저것", 
            "그것", "우리", "여러분", "이번", "다음", "지금", "때문", "정도", "이런", "저런"
        }

        candidates = []
        for word, freq in word_freq.items():
            if word in stop_words:
                continue
            if re.search(r'[a-zA-Z]', word) or (len(word) >= 2 and freq >= 1):
                candidates.append(word)
                
        print(f"총 {len(candidates)}개의 핵심 후보 단어 추출 완료.")
        return candidates

    def _chunk_list(self, data_list, chunk_size):
        for i in range(0, len(data_list), chunk_size):
            yield data_list[i:i + chunk_size]

    def build_or_update_dictionary(self, chunk_size=50, save_path="term_mapping_dict.json"):
        file_list, scripts = self._load_and_clean_scripts()
        if not scripts:
            print("처리할 텍스트가 없습니다.")
            return {}

        # 메타데이터로부터 session_topics 문자열 생성
        session_topics = self._get_session_topics(file_list)

        master_dict = {}
        existing_words = set()
        
        if os.path.exists(save_path):
            try:
                with open(save_path, "r", encoding="utf-8") as f:
                    master_dict = json.load(f)
                    for standard, variations in master_dict.items():
                        existing_words.add(standard)
                        existing_words.update(variations)
                print(f"기존 사전 로드 완료 (학습된 단어 {len(existing_words)}개 포함)")
            except json.JSONDecodeError:
                print("기존 사전 파일이 비어있거나 손상되어 새로 시작합니다.")
                master_dict = {}

        candidate_words = self._extract_jargon_candidates(scripts)
        new_candidates = [w for w in candidate_words if w not in existing_words]
        print(f"전체 추출 단어: {len(candidate_words)}개 -> 신규 처리 대상 단어: {len(new_candidates)}개")

        if new_candidates:
            print("\nLLM 매핑 사전 생성 중...")
            #prompt = PromptTemplate.from_template("""

            # 1. 시스템 프롬프트: 역할, 규칙, 예시, 출력 형식(CoT 포함)을 꼼꼼하게 정의
            system_prompt = SystemMessagePromptTemplate.from_template("""
            당신은 IT 개발 강의(Java, Spring, Database 등)의 STT(음성 인식) 데이터 전처리 전문가입니다.
            주어진 STT 텍스트 파편들을 분석하여, 발음 기반의 오인식 결과물이나 한/영 혼용 표기를 정확한 IT 표준 전문 용어(대소문자 준수)로 매핑하는 역할을 수행합니다.
                                                                      
            매핑되는 용어들은 [현재 처리 중인 강의 세션 주제 정보]의 문맥에 맞아야 합니다.
            {session_topics}
            
            주어진 단어 리스트는 위 강의 주제들의 STT 스크립트에서 추출된 단어들입니다. 
            음성 인식 과정에서 발생한 발음 기반의 오타, 한/영 혼용 표기, 띄어쓰기 오류를 역추적하여 원래의 'IT 전문 용어(표준어)'로 묶어주세요.
            
            [환각(Hallucination) 원천 차단 STT 매핑 핵심 규칙]
            1. 엄격한 단어 제한 : "변이어" 리스트에는 오직 입력된 [처리할 STT 추출 단어 리스트]에 존재하는 단어만 정확히 일치하는 철자로 넣어야 합니다. 당신이 스스로 새로운 오타나 유사어를 창조해내는 것을 엄격히 금지합니다.
            2. 발음 유사성 역추적: 강사가 영어로 말한 IT 용어를 STT가 소리 나는 대로 한글로 적은 경우(예: 크루드 -> CRUD, 엔티티 -> Entity, 데코레이터 -> Decorator)를 복원하세요.
            3. 한/영 파편화 복구: 영문 알파벳과 한글이 섞인 형태(예: N아I어 -> NIO, 마I에S큐L -> MySQL)를 유추하세요.
            4. 문맥 기반 추론: 매핑 결과를 도출할 때는 반드시 [강의 세션 주제 정보]의 내용을 최우선 힌트로 삼아, 주제와 연관된 전문 용어를 추론하세요.
            5. 표준어 표기 원칙: 매핑되는 표준 IT 용어는 공식적인 영문 대소문자 표기를 따르세요.
            6. 노이즈 철저 배제: 일반 명사(사과, 책상), 숫자(1번, 100), 강의 진행용어(진행, 결과, 질문)는 결과에 절대 포함하지 마세요.
            7. 억지 매핑 금지 (Contextual Rejection): 추출된 단어 중, 강의 주제와 전혀 무관한 일반 명사(사과, 책상), 숫자(1번), 진행용어(질문, 결과)가 섞여 있다면 억지로 표준 용어에 매핑하지 말고 제외하세요.
            8. 번역 및 합성어 통합: 한국어 뜻(예: 관리자 -> Admin)이나 띄어쓰기가 다른 합성어(예: 인포메이션 스키마 -> Information Schema)는 문맥이 맞다면 하나의 표준 용어로 묶어주세요.



            입력 단어 리스트: {words}
                                                                      
            [Few-Shot 예시]
            - STT 발화 오류: ["크루드", "씨알유디", "제이D비C", "마I에S큐L", "엔티티", "버퍼"]
            - 주제: Java Database Connectivity
            - 출력 예시:

                                                                      
            결과 형식 (반드시 유효한 JSON 포맷만 출력):
            {{
                "표준용어1": ["변이어1", "변이어2", ...],
                "표준용어2": ["변이어1", "변이어2", ...]
            }}
            반드시 위 예시와 동일한 JSON 형식으로만 응답하세요.
            """)

            # 2. 휴먼 프롬프트: 동적 데이터(주제, 단어 리스트)만 주입
            human_prompt = HumanMessagePromptTemplate.from_template("""
            [강의 세션 주제 정보]
            {session_topics}

            [처리할 STT 추출 단어 리스트]
            {words}

            지시사항: 위 [처리할 STT 추출 단어 리스트]에 존재하는 단어만을 사용하여 그룹화하세요. 리스트에 없는 단어를 지어내면 안 됩니다.
            """)

            # 3. 프롬프트 결합
            chat_prompt = ChatPromptTemplate.from_messages([system_prompt, human_prompt])

            for idx, chunk in enumerate(self._chunk_list(new_candidates, chunk_size)):
                print(f"[{idx+1}] 청크 처리 중...")
                try:
                    # LLM 호출 부분 session_topics 변수를 chat_prompt.format_prompt에 동적으로 주입
                    response = self.llm.invoke(chat_prompt.format_prompt(
                        session_topics=session_topics, 
                        words=", ".join(chunk)
                    ))
                    clean_text = response.content.replace("```json", "").replace("```", "").strip()
                    chunk_dict = json.loads(clean_text)
                    
                    for standard, variations in chunk_dict.items():
                        if standard in master_dict:
                            master_dict[standard] = list(set(master_dict[standard] + variations))
                        else:
                            master_dict[standard] = variations
                except Exception as e:
                    print(f"청크 에러: {e}")

            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(master_dict, f, ensure_ascii=False, indent=4)
            print(f"\n사전이 '{save_path}'에 성공적으로 저장되었습니다.")
        else:
            print("\n새롭게 추가할 전문용어가 없어 기존 사전을 그대로 유지합니다.")
        
        return master_dict
    

# ==========================================
# 2. 룰베이스 전처리 클래스
# ==========================================
class RuleBasedPreprocessor:
    def __init__(self, dict_path="term_mapping_dict.json"):
        # 저장된 JSON 사전을 불러와 역매핑(Reverse Mapping) 구조 생성
        with open(dict_path, "r", encoding="utf-8") as f:
            mapping_dict = json.load(f)
            
        self.reverse_map = {}
        for standard, variations in mapping_dict.items():
            for var in variations:
                self.reverse_map[var] = standard
            self.reverse_map[standard] = standard # 표준어 자체도 등록

        # 변이어 길이가 긴 것부터 치환되도록 정렬 (예: '마이에스큐엘'이 '마이'보다 먼저 탐색됨)
        sorted_vars = sorted(self.reverse_map.keys(), key=len, reverse=True)
        
        # 정규표현식 패턴 컴파일 (고속 치환용)
        # 단어가 많을 경우 re.escape로 특수문자를 안전하게 처리합니다.
        self.pattern = re.compile("|".join(re.escape(var) for var in sorted_vars))

    def _replace_match(self, match):
        """매칭된 단어를 표준어로 변환"""
        return self.reverse_map[match.group(0)]

    def process_text(self, text):
        """단일 텍스트 문자열 전처리"""
        if not text: return ""
        return self.pattern.sub(self._replace_match, text)

    def process_files(self, input_folder, output_folder):
        """폴더 내 모든 스크립트를 전처리하여 새 폴더에 저장"""
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)

        file_list = glob.glob(os.path.join(input_folder, "*.txt"))
        print(f"\n총 {len(file_list)}개의 파일 전처리를 시작합니다...")

        for file_path in file_list:
            file_name = os.path.basename(file_path)
            output_path = os.path.join(output_folder, file_name)
            
            with open(file_path, 'r', encoding='utf-8') as fin, \
                 open(output_path, 'w', encoding='utf-8') as fout:
                
                for line in fin:
                    # 화자 정보나 타임스탬프 등 원본 메타데이터를 유지한 상태에서 단어만 치환
                    processed_line = self.process_text(line)
                    fout.write(processed_line)
                    
        print(f"전처리가 완료되어 [{output_folder}]에 저장되었습니다.")