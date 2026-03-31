import json
import os

os.makedirs("./temp_test_input", exist_ok=True)
file_path = "./script/raw/test_cases_nlp.jsonl"

try:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    # 데이터가 배열인지 JSONL인지 자동 판별
    if content.startswith("["):
        data = json.loads(content)
    else:
        data = [json.loads(line) for line in content.split('\n') if line.strip()]

    # 파일 쪼개서 저장
    for item in data:
        t_id = item.get("test_id", "unknown_id")
        script = item["input"]["script"]
        with open(f"./temp_test_input/{t_id}.txt", "w", encoding="utf-8") as out:
            out.write(script)

    print(f"✅ 성공: 총 {len(data)}개의 파일이 ./temp_test_input 폴더에 생성되었습니다.")
except Exception as e:
    print(f"❌ 에러 발생: {e}")
