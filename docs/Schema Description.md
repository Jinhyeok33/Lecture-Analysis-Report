## NLP 분석 엔진 출력 json 형식 예시
```json
{
  "lecture_id": "2026-02-02_kdt-backendj-21th",
  "language_quality": {
    "repeat_expressions": {
      "이제": 42,
      "그래서": 36,
      "어쨌든": 11
    },
    "repeat_ratio": 0.18,
    "incomplete_sentence_ratio": 0.05,
    "speech_style_ratio": {
      "formal": 0.92,
      "informal": 0.08
    }
  },

  "concept_clarity_metrics": {
    "speech_rate_wpm": 176
  },


  "interaction_metrics": {
    "understanding_question_count": 21
  }
}
```

## LLM 분석 엔진 최종 출력 json 형식 예시
```json
{
  "llm_aggregated_analysis": {
    "summary_scores": {
      "lecture_structure": {
        "learning_objective_intro": 3.8,
        "previous_lesson_linkage": 3.1,
        "explanation_sequence": 4.0,
        "key_point_emphasis": 3.4,
        "closing_summary": 2.7
      },
      "concept_clarity": {
        "concept_definition": 4.1,
        "analogy_example_usage": 3.6,
        "prerequisite_check": 3.3
      },
      "practice_linkage": {
        "example_appropriateness": 4.0,
        "practice_transition": 3.5,
        "error_handling": 3.2
      },
      "interaction": {
        "participation_induction": 2.8,
        "question_response_sufficiency": 3.0
      }
    },
    "overall_strengths": [],
    "overall_issues": [],
    "overall_evidences": []
  }
}
```