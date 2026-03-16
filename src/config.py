# C:\Repositories\NLP-internship\src\config.py

import os

# 1. 이 파일(config.py)이 있는 위치 (src 폴더)
SRC_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. 프로젝트 최상위 폴더 (NLP-internship)
PROJECT_ROOT = os.path.dirname(SRC_DIR)

# 3. 공통으로 사용할 경로들 미리 다 만들어두기
SCRIPT_DIR = os.path.join(PROJECT_ROOT, "script")
RAW_DATA_DIR = os.path.join(SCRIPT_DIR, "raw")
OUTPUT_NLP_DIR = os.path.join(SCRIPT_DIR, "output_NLP")

# 나중에 다른 엔진이 추가되면 여기에 한 줄만 추가하기
# OUTPUT_VISION_DIR = os.path.join(SCRIPT_DIR, "output_Vision")

# 폴더가 없으면 미리 만들어두기
os.makedirs(OUTPUT_NLP_DIR, exist_ok=True)

