import os
import asyncio
from dotenv import load_dotenv
from .preprocessing import DictionaryGenerator, RuleBasedPreprocessor

# .env 파일의 내용을 환경 변수로 불러옵니다.
# 이 코드가 ChatOpenAI가 호출되기 전에 실행되어야 합니다.
load_dotenv()

def main():
    # 1. 절대 경로 설정
    BASE_DIR = "/workspaces/NLP-internship"
    
    RAW_DIR = os.path.join(BASE_DIR, "script/raw")
    PREPROCESSED_DIR = os.path.join(BASE_DIR, "script/preprocessed")
    
    # 리소스(단어 사전) 폴더 및 파일 경로
    RESOURCE_DIR = os.path.join(BASE_DIR, "resources")
    DICT_PATH = os.path.join(RESOURCE_DIR, "term_mapping_dict.json")

    # 메타데이터 CSV 파일 경로 설정
    METADATA_PATH = os.path.join(BASE_DIR, "강의 메타데이터.csv")


    # 필요한 폴더가 없다면 자동 생성
    os.makedirs(PREPROCESSED_DIR, exist_ok=True)
    os.makedirs(RESOURCE_DIR, exist_ok=True)

    print("=== 전처리 파이프라인 시작 ===")

    # 2. 단어 사전 생성 (사전 파일이 없는 경우에만 실행)
#    if not os.path.exists(DICT_PATH):
#        print(f"\n[1단계] '{DICT_PATH}'가 존재하지 않아 LLM 기반 단어 사전을 생성합니다.")
#        # max_features는 추출할 후보 단어의 수입니다. 스크립트 규모에 맞게 조정하세요.
#        generator = DictionaryGenerator(raw_folder_path=RAW_DIR, max_features=1500)
#        generator.build_dictionary(chunk_size=200, save_path=DICT_PATH)
#        print("\n💡 TIP: 생성된 JSON 파일을 열어 잘못 매핑된 단어가 없는지 꼭 눈으로 확인하고 수정하세요!")
#    else:
#        print(f"\n[1단계] '{DICT_PATH}' 사전 파일이 이미 존재하여 생성을 건너뜁니다.")
#        print("💡 TIP: 새로운 원본 데이터가 대량으로 추가되었다면 기존 JSON 파일을 삭제하고 다시 실행하세요.")

    # 1. 단어 사전 업데이트 (알아서 신규 단어만 추가함)
    print("\n[1단계] LLM 기반 단어 사전 생성 및 업데이트를 진행합니다.")
    generator = DictionaryGenerator(raw_folder_path=RAW_DIR, metadata_path=METADATA_PATH, llm_model="gpt-4o-mini")
    # 바뀐 메서드 이름(build_or_update_dictionary) 호출
    #generator.build_or_update_dictionary(chunk_size=200, save_path=DICT_PATH)

    # 일반 함수 호출 대신 asyncio.run()으로 비동기 함수 실행
    asyncio.run(generator.build_or_update_dictionary_async(
        chunk_size=50, 
        save_path=DICT_PATH, 
        max_concurrency=5 # OpenAI API 티어에 따라 이 값을 10~20으로 늘리면 속도가 훨씬 빨라집니다.
    ))


    # 3. 룰베이스 기반 전처리 진행 (항상 실행)
    print(f"\n[2단계] 생성된 사전을 바탕으로 스크립트 전처리를 시작합니다.")
    preprocessor = RuleBasedPreprocessor(dict_path=DICT_PATH)
    preprocessor.process_files(input_folder=RAW_DIR, output_folder=PREPROCESSED_DIR)
    
    print("\n=== 전처리 파이프라인 완료 ===")

if __name__ == "__main__":
    main()