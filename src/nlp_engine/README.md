# NLP Engine

NLP analysis module migrated from `dev/hs`.

## Run

```bash
python -m src.nlp_engine data/raw
```

## Output

JSON files are written to `data/outputs/nlp`.

### ERD
| column                        | type          | description                                 |
|:------------------------------|:--------------|:--------------------------------------------|
| lecture_id                    | varchar(200)  |                                             |
| language_quality              | dict          | 1. 언어 표현 품질                            |
| └ repeat_expressions          | dict          | 불필요한 반복표현(필러) 목록                  |
| └ total_sentences             | int           | 전체 문장 수                                 |
| └ total_token_count           | int           | 전체 토큰 수                                 |
| └ total_filler_count          | int           | 전체 필러 수                                 |
| └ repeat_ratio                | DECIMAL(5, 4) | 전체 문장 대비 필러 단어 수                   |
| └ repeat_density              | DECIMAL(5, 4) | 전체 토큰 대비 필러 단어 수(채택)             |
| └ score_1_1                   | int           | 언어 정제도 점수  repeat_expressions         |
| └ incomplete_sentence_ratio   | DECIMAL(4, 3) | 발화미완결문장수 = 1 - "speech_style_ratio"  |
| └ score_1_2                   | int           | 발화완결성 점수 utterance_completeness       |
| └ speech_style_ratio          | dict          | 발화스타일 비율 = "formal" + "informal"      |
| └ └ formal                    | DECIMAL(4, 3) | formal한 발화 완결 문장 수                   |
| └ └ informal                  | DECIMAL(4, 3) | informal한 발화 완결 문장 수                 |
| └ └ score_1_3                 | int           | 언어 일관성 점수 speech_style_consistency                            |
| concept_clarity_metrics       | dict          | 3. 개념 설명 명확성                          |
| └ speech_rate_wpm             | int           | 분당 발화 수                                 |
| └ classification              | varchar(200)  | 분당 발화 수의 범위 구간                      |
| └ score_3_4                   | int           | 발화속도 적절성(speech_rate_appropriateness) 점수 | 
| interaction_metrics           | dict          | 5. 수강생 상호작용                           |
| └ understanding_question_count| int           | 이해 질문 수                                 |
| └ score_5_1                   | int           | 이해 확인 충분성 점수  understanding_question                       |



# 강의 품질 평가 Rubric 명세서
5개의 카테고리, 총 18개의 평가 항목을 기준으로 나눈 점수 체계표이다.
NLP엔진 부분만 발췌하였다.
- 점수 체계: 5점(매우 우수) ~ 1점(매우 미흡)
- 가중치: 높음 / 중간 / 낮음

## 1. 언어 표현 품질

### 1.1 불필요한 반복 표현
- **항목 ID**: `repeat_expressions`
- **카테고리**: 언어 표현 품질
- **가중치**: 높음
- **평가 기준**: 동일 단어·문장 및 "이제", "그래서" 등 특정 표현을 과도하게 반복하지 않는가.
- **점수 rubric**
  - **5점**: 동일 표현의 반복이 거의 없고, 표현 선택이 다양하며 전달 흐름이 자연스럽다. (RD < 0.01 정제된 언어)
  - **4점**: 일부 반복 표현이 있으나 강의 이해를 방해할 정도는 아니다. (0.01 ≤ RD < 0.03	자연스러움)
  - **3점**: 반복 표현이 눈에 띄며, 일부 구간에서 전달의 밀도나 집중도를 떨어뜨린다. (0.03 ≤ RD < 0.06	반복 감지)
  - **2점**: 특정 단어·문장 반복이 잦아 강의 흐름이 단조롭고 전달력이 약해진다. (0.06 ≤ RD < 0.10 단조로움)
  - **1점**: 반복 표현이 매우 빈번하여 내용 전달과 수강 집중을 뚜렷하게 방해한다. (RD ≥ 0.10	전달 불능)

### 1.2 발화 완결성
- **항목 ID**: `utterance_completeness`
- **카테고리**: 언어 표현 품질
- **가중치**: 중간
- **평가 기준**: 문장이 완결된 형태로 끝맺음되는가(중간에 끊기지 않는가).
- **점수 rubric**
  - **5점**: 대부분의 발화가 문법적·의미적으로 완결되어 있으며 끊김이 거의 없다. 
  - **4점**: 간헐적 끊김은 있으나 전반적으로 문장이 완결된 형태를 유지한다.
  - **3점**: 미완결 문장이 반복적으로 나타나지만 전체 이해는 가능하다.
  - **2점**: 끊긴 문장이나 미완결 발화가 잦아 의미 해석에 자주 부담을 준다.
  - **1점**: 발화가 자주 중단되거나 끝맺음되지 않아 강의 이해가 크게 저해된다.

### 1.3 언어 일관성
- **항목 ID**: `speech_style_consistency`
- **카테고리**: 언어 표현 품질
- **가중치**: 중간
- **평가 기준**: 강의 전반에 걸쳐 존댓말/반말이 일관되게 사용되는가.
- **점수 rubric**
  - **5점**: 강의 전반에서 화법이 일관되며 어조 전환이 거의 없다.
  - **4점**: 일부 어조 전환이 있으나 전반적 일관성은 유지된다.
  - **3점**: 존댓말과 반말이 혼용되지만 심각한 수준은 아니다.
  - **2점**: 어조 전환이 잦아 강의 톤이 불안정하게 느껴진다.
  - **1점**: 화법 일관성이 거의 없고, 청자 입장에서 강의 태도가 산만하게 느껴진다.

## 3. 개념 설명 명확성

### 3.4 발화 속도 적절성
- **항목 ID**: `speech_rate_appropriateness`
- **카테고리**: 개념 설명 명확성
- **가중치**: 중간
- **평가 기준**: 타임스탬프 기준 분당 발화량이 수강생이 따라가기 적절한 수준인가.
- **점수 rubric**
  - **5점**: 발화 속도가 안정적이며 수강생이 내용을 따라가기에 매우 적절하다.
  - **4점**: 전반적으로 적절한 속도를 유지하나 일부 구간의 편차가 있다.
  - **3점**: 속도 편차가 눈에 띄지만 전체 학습 진행은 가능하다.
  - **2점**: 지나치게 빠르거나 느린 구간이 잦아 이해 흐름이 자주 끊긴다.
  - **1점**: 발화 속도가 전반적으로 부적절하여 강의 이해를 크게 저해한다.

## 5. 수강생 상호작용

### 5.1 이해 확인 질문
- **항목 ID**: `understanding_question`
- **카테고리**: 수강생 상호작용
- **가중치**: 높음
- **평가 기준**: 수강생의 이해 여부를 확인하는 질문을 적절히 하는가.
- **점수 rubric**
  - **5점**: 이해 확인 질문이 적절한 시점에 반복적으로 제시되어 학습 상태 점검이 분명하다.
  - **4점**: 이해 확인 질문이 전반적으로 적절하게 이루어진다.
  - **3점**: 이해 확인 질문은 있으나 빈도나 타이밍이 제한적이다.
  - **2점**: 형식적 질문은 있으나 실제 이해 점검 기능은 약하다.
  - **1점**: 이해 여부를 확인하는 질문이 거의 없다.




## 출력예시

{
  "lecture_id": "2026-02-02_kdt-backendj-21th",
  "language_quality": {
    "repeat_expressions": {
      "이제": 140,
      "그래서": 156,
      "좀": 83,
      "일단": 81,
      "그러면": 73,
      "그": 10,
      "네": 3,
      "뭐": 102,
      "아이": 5,
      "이": 5,
      "약간": 12,
      "아": 21,
      "그러니까": 30,
      "어": 34,
      "오": 2,
      "애고": 1,
      "자": 37,
      "그렇지": 17,
      "옳지": 10,
      "어어": 1,
      "얘": 4,
      "음": 1,
      "그지": 4,
      "에": 1,
      "야": 2,
      "아이고": 1,
      "사실": 10,
      "어쨌든": 3,
      "저": 5,
      "아니": 1,
      "저기": 1,
      "그래": 2,
      "아우": 1,
      "마": 1,
      "하": 1,
      "오케이": 2,
      "와": 1,
      "예": 2,
      "워": 1,
      "거": 1
    },
    "total_sentences": 1787,
    "total_token_count": 55789,
    "total_filler_count": 868,
    "repeat_ratio": 0.4857,         
    "repeat_density": 0.0156,
    "score_1_1" : 3
    "incomplete_sentence_ratio": 0.466,  
    "score_1_2" :  
    "speech_style_ratio": {               
      "formal": 0.2,
      "informal": 0.334,
      "score_1_3" : 3
    }
  },
  "concept_clarity_metrics": {
    "speech_rate_wpm": 98,
    "classification": "very_low",
    "score": 3
  },
  "interaction_metrics": {
    "understanding_question_count": 24
    "score" : 3
  }
}