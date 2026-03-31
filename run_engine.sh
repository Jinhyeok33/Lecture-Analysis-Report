#!/bin/bash

echo "=== NLP 엔진 배치 분석을 시작합니다 ==="

# 1. src 폴더로 이동
cd /workspaces/NLP-internship/src

# 2. 엔진 실행 (폴더 경로)
python -m engine_NLP "/workspaces/NLP-internship/script/raw"

echo "=== 분석이 완료되었습니다 ==="