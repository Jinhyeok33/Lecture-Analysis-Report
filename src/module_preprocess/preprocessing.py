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
        
        # 메타데이터를 메모리에 한 번만 로드하여 속도 최적화
            # _get_session_topics_for_file(self, file_path): 내부 try: df = pd.read_csv(self.metadata_path, encoding='utf-8-sig') 로 구현되었으나
            # _get_session_topics_for_file이 여러 번 호출될 경우, 매번 CSV를 읽게되어 비효율적입니다.
            # __init__에서 한 번만 읽어두는 방식으로 변경
        try:
            self.metadata_df = pd.read_csv(self.metadata_path, encoding='utf-8-sig')
            print("[초기화] 메타데이터 로드 완료")
        except Exception as e:
            print(f"[초기화 실패] 메타데이터 로드 에러: {e}")
            self.metadata_df = pd.DataFrame()

    def _get_session_topics_for_file(self, file_path):
        """단일 파일의 이름(date_course_id.txt)을 파싱하여 CSV에서 해당 파일의 주제와 내용만 추출합니다."""
        if self.metadata_df.empty: return "강의 정보 없음"

        topics_set = set()
        
        # 1. 파일 경로에서 순수 파일명만 추출 (예: 2026-02-02_kdt-backendj-21th.txt -> 2026-02-02_kdt-backendj-21th)
        filename = os.path.basename(file_path).replace('.txt', '')
        parts = filename.split('_')
        
        # 2. 날짜와 코스 ID 분리
        if len(parts) >= 2:
            date_str = parts[0]
            course_id = parts[1]
            
            # 3. 데이터프레임에서 해당 날짜, 코스 ID와 일치하는 행 필터링
            matched = df[(df['date'] == date_str) & (df['course_id'] == course_id)]
            
            # 4. 일치하는 모든 세션(오전/오후)의 주제와 내용을 세트에 추가
            for _, row in matched.iterrows():
                subject = str(row['subject']).strip()
                content = str(row['content']).strip()
                topics_set.add(f"- [{subject}] {content}")
                
        # 5. 결과 반환
        if topics_set:
            return "\n".join(sorted(list(topics_set)))
        
        return "강의 정보 없음"

    def _load_and_clean_single_file(self, file_path):
        sentences = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                clean_text = self.meta_pattern.sub('', line)
                if clean_text: sentences.append(clean_text)
        return sentences

    def _extract_jargon_candidates(self, scripts):
        print("\n[단어 추출] 룰베이스 어절 추출 및 조사 제거를 시작합니다...")
        word_freq = {}
        
        for text in scripts:
            clean_text = re.sub(r'[^a-zA-Z가-힣0-9\s]', ' ', text)
            words = clean_text.split()
            
            for w in words:
                #w = re.sub(r'(은|는|이|가|을|를|에|에서|로|으로|부터|까지|도|만|의|입니다|합니다|습니다|다|고|며|면)$', '', w)

                pattern = r'(입니다|습니다|합니다|이라서|이니까|이잖아|에다가|에다|에서|부터|까지|마다|로서|로써|보다|처럼|라는|다는|랑|이랑|라서|니까|잖아|은|는|이|가|을|를|에|로|으로|도|만|의|다|고|며|면|야|쯤|용|할|단|인|니)$'
                while re.search(pattern, w):
                    w = re.sub(pattern, '', w)
                
                w = w.strip('.')
                
                if len(w) < 2 or len(w) > 15:
                    if not re.search(r'[a-zA-Z]', w): continue
                if w.isdigit(): continue
                    
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

    # 리스트 자르기용 유틸리티 메서드
    def _chunk_list(self, data_list, chunk_size):
        for i in range(0, len(data_list), chunk_size):
            yield data_list[i:i + chunk_size]

    async def _process_chunk_async(self, chat_prompt, session_topics, chunk, semaphore, master_dict, existing_words, file_lock, save_path):
        """개별 청크를 비동기적으로 LLM에 요청하고 마스터 사전에 병합합니다."""
        async with semaphore: # 동시에 실행되는 코루틴 개수 제한
            try:
                response = await self.llm.ainvoke(chat_prompt.format_prompt(
                    session_topics=session_topics, 
                    words=", ".join(chunk)
                ))
                clean_text = response.content.replace("```json", "").replace("```", "").strip()
                chunk_dict = json.loads(clean_text)
                
                # 병합 로직
                for standard, content in chunk_dict.items():
                    variations = content.get("variations", []) if isinstance(content, dict) else content
                    
                    if standard in master_dict:
                        old_vars = master_dict[standard].get("variations", []) if isinstance(master_dict[standard], dict) else master_dict[standard]
                        merged_vars = list(set(old_vars + variations))
                        master_dict[standard] = {"variations": merged_vars, "reason": content.get("reason", "업데이트됨")}
                    else:
                        master_dict[standard] = {"variations": variations, "reason": content.get("reason", "")}
                        
                    existing_words.add(standard)
                    existing_words.update(variations)
                # 파일 충돌을 막기 위해 Lock을 걸고 안전하게 중간 저장 수행
                async with file_lock:
                    with open(save_path, "w", encoding="utf-8") as f:
                        json.dump(master_dict, f, ensure_ascii=False, indent=4)
                # -----------------------------
            except Exception as e:
                print(f"청크 처리 중 에러 발생: {e}")

    async def build_or_update_dictionary_async(self, chunk_size=50, save_path="term_mapping_dict.json", max_concurrency=5):
        # 1. glob을 이용해 해당 폴더의 텍스트 파일 목록만 먼저 싹 가져옵니다.
        file_list = glob.glob(os.path.join(self.raw_folder_path, "*.txt"))
        if not file_list:
            print("처리할 텍스트 파일이 없습니다.")
            return {}

        # 메타데이터로부터 session_topics 문자열 생성
        # session_topics = self._get_session_topics(file_list)

        master_dict = {}
        existing_words = set()
        
        if os.path.exists(save_path):
            try:
                with open(save_path, "r", encoding="utf-8") as f:
                    master_dict = json.load(f)
                    for standard, content in master_dict.items():
                        variations = content.get("variations", []) if isinstance(content, dict) else content
                        existing_words.add(standard)
                        existing_words.update(variations)
                print(f"기존 사전 로드 완료 (단어 {len(existing_words)}개)")
            except json.JSONDecodeError:
                print("기존 사전 파일이 비어있거나 손상되어 새로 시작합니다.")
                master_dict = {}

        print("\n[주제별 단어 집계] 파일들을 분석합니다...")
        topic_to_words = {}

        # 카운트를 위한 변수 추가
        total_candidate_count = 0

        # 파일별로 순회하며 주제와 단어 집계
        for file_path in file_list:
            # 1. 단일 파일용 메서드 호출 (_get_session_topics_for_file)
            session_topics = self._get_session_topics_for_file(file_path)
            # 2. 단일 파일 스크립트 로드 (_load_and_clean_single_file)
            scripts = self._load_and_clean_single_file(file_path)
            # 3. 단어 추출 (_extract_jargon_candidates)
            candidate_words = self._extract_jargon_candidates(scripts)
            
            # 이번 파일에서 추출된 단어 수 누적
            total_candidate_count += len(candidate_words)
            
            new_candidates = [w for w in candidate_words if w not in existing_words]
            if new_candidates:
                if session_topics not in topic_to_words: topic_to_words[session_topics] = set()
                # set 업데이트 시 중복이 자동으로 제거됨
                topic_to_words[session_topics].update(new_candidates)

        # 주제별로 잘 묶인 최종 신규 단어(중복 제거됨)의 총 개수 계산
        total_new_count = sum(len(words) for words in topic_to_words.values())

        print(f"-> 전체 추출 단어: {total_candidate_count}개 -> 신규 처리 대상 단어: {total_new_count}개")
        print("\nLLM 구동 및 매핑 사전 생성 중...")

        # 1. 시스템 프롬프트: 역할, 규칙, 예시, 출력 형식(CoT 포함)을 꼼꼼하게 정의
        system_prompt = SystemMessagePromptTemplate.from_template("""
        당신은 IT 개발 강의(Java, Spring, Database 등)의 STT(음성 인식) 데이터 전처리 전문가입니다.
        주어진 STT 텍스트 파편들을 분석하여, 발음 기반의 오인식 결과물이나 한/영 혼용 표기를 정확한 IT 표준 전문 용어(대소문자 준수)로 매핑하는 역할을 수행합니다.
            
        [STT 매핑 핵심 규칙]
        1. 발음 유사성 역추적: 강사가 영어로 말한 IT 용어를 STT가 소리 나는 대로 한글로 적은 경우(예: 크루드 -> CRUD, 엔티티 -> Entity, 데코레이터 -> Decorator)를 복원하세요.
        2. 한/영 파편화 복구: 영문 알파벳과 한글이 섞인 형태(예: N아I어 -> NIO, 마I에S큐L -> MySQL)를 유추하세요.
        3. 문맥 기반 추론(매우 중요): 매핑 결과를 도출할 때는 반드시 [강의 세션 주제 정보]의 내용을 최우선 힌트로 삼아, 주제와 연관된 전문 용어를 추론하세요.
        4. 표준어 표기 원칙: 매핑되는 표준 IT 용어는 공식적인 영문 대소문자 표기를 따르세요.
        5. 합성어 및 번역어 통합: 여러 단어가 합쳐진 용어(예: 인포메이션 스키마 -> Information Schema)나, 한국어 뜻(예: 관리자 -> Admin)도 하나의 표준 용어로 매핑하세요.
        6. 노이즈 철저 배제: 일반 명사(사과, 책상), 숫자(1번, 100), 강의 진행용어(진행, 결과, 질문)는 결과에 절대 포함하지 마세요.
            
                                                                      
        [Few-Shot 예시]
        - STT 발화 오류: ["크루드", "씨알유디", "제이D비C", "마I에S큐L", "엔티티", "버퍼"]
        - 주제: Java Database Connectivity
        - 출력 예시:
        {{                                                
            "Entity": [
                "엔T",
                "엔티티",
                "엔티T",
                "..."
            ],
            "MySQL": [
                "마이스큐엘",
                "마이스큐L",
                ...,
            ]
        }}
                                                                                                                               
        [결과 형식] (반드시 유효한 JSON 포맷만 출력):
        {{
            "표준용어1": ["변이어1", "변이어2", ...],
            "표준용어2": ["변이어1", "변이어2", ...]
        }}
                                                                      
        반드시 위 결과 형식과 동일한 JSON 형식으로만 응답하세요.
        """)

        # 2. 휴먼 프롬프트: 그때그때 바뀌는 동적 데이터(주제, 단어 리스트)만 주입
        human_prompt = HumanMessagePromptTemplate.from_template("""
        [강의 세션 주제 정보]
        {session_topics}
                                                                    
        [처리할 STT 추출 단어 리스트]
        {words}

        [지시사항]                                               
        1. [처리할 STT 추출 단어 리스트]는 위 [강의 세션 주제 정보]들의 STT 스크립트에서 추출된 단어들입니다. 
        음성 인식 과정에서 발생한 발음 기반의 오타, 한/영 혼용 표기, 띄어쓰기 오류를 역추적하여 원래의 'IT 전문 용어(표준어)'로 묶어주세요.
        2. 위 [처리할 STT 추출 단어 리스트]에 있는 단어'만'을 사용하여 변이어(variations)를 구성하세요. 주제 정보를 변이어로 가져오지 마세요.                                                                                                             
        """)

        # 3. 프롬프트 결합
        chat_prompt = ChatPromptTemplate.from_messages([system_prompt, human_prompt])
        semaphore = asyncio.Semaphore(max_concurrency)
        tasks = []

        file_lock = asyncio.Lock()

        for topic, words_set in topic_to_words.items():
            words_list = list(words_set)
            for chunk in self._chunk_list(words_list, chunk_size):
                tasks.append(asyncio.create_task(
                    self._process_chunk_async(chat_prompt, topic, chunk, semaphore, master_dict, existing_words, file_lock, save_path)
                ))

        # 이후 생성된 task들을 모아서 한 번에 실행(gather)하는 부분
        if tasks:
            print(f"\n[비동기 처리] {len(tasks)}개 청크 병렬 실행 (최대 동시: {max_concurrency})")
            await asyncio.gather(*tasks)
            
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(master_dict, f, ensure_ascii=False, indent=4)
            print(f"\n사전이 '{save_path}'에 저장되었습니다.")
        else:
            print("새롭게 추가할 용어가 없습니다.")
            
        return master_dict
        """ 
        비동기처리 이전 로직
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
        """    

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