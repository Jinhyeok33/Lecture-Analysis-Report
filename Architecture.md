lecture_nlp_analyzer/
├── script/                # 데이터 관리
│   ├── raw/               # 원본 강의 텍스트/스크립트 (파일이 업로드되면 등록되는곳)
│   ├── preprocessed/      # 전처리 완료된 데이터
│   └── output/            # 분석 결과 리포트 (JSON, PDF 등)
├── src/                   # 핵심 소스 코드
│   ├── preprocess/        # 전처리 모듈
│   │   ├── parser.py      # 텍스트 추출 및 정제
│   │   └── eda_generator.py # 기초 통계 분석
│   └── engine/            # 분석 엔진
│       ├── analyzer.py    # 메인 분석 로직
│       ├── expression.py  # 표현력 분석 (어휘 다양성 등)
│       ├── clarity.py     # 전달력/명확성 분석
│       └── interaction.py # 상호작용 및 흐름 분석
├── tests/                 # 유닛 테스트 코드
├── config/                # 설정 파일 (API 키, 하이퍼파라미터 등)
├── Dockerfile             # 컨테이너화 설정
├── requirements.txt       # 의존성 패키지 목록
└── main.py                # 전체 프로세스 실행 엔트리포인트