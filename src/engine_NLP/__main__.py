import sys
import os
import glob
from .integrated_engine import IntegratedNLPEngine

def main():
    if len(sys.argv) < 2:
        print("사용법: python -m engine_NLP <파일_또는_폴더_경로>")
        sys.exit(1)

    path = sys.argv[1]
    engine = IntegratedNLPEngine()

    # 입력된 경로가 폴더면 .txt 전체 검색, 파일이면 해당 파일만 리스트에 넣음
    files = glob.glob(os.path.join(path, "*.txt")) if os.path.isdir(path) else [path]

    if not files:
        print("분석할 .txt 파일이 없습니다. 경로를 확인해주세요.")
        return

    print(f"--- 총 {len(files)}개 파일 분석 시작 ---")
    for file_path in files:
        fname = os.path.basename(file_path)
        try:
            print(f"진행 중: {fname}...", end=" ")
            engine.analyze_all(file_path)
            print(f"✅ 완료")
        except Exception as e:
            print(f"❌ 실패 ({e})")

if __name__ == "__main__":
    main()



'''
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

'''