# Data Contract

## NLP output (`data/outputs/nlp/*_nlp.json`)

```json
{
  "lecture_id": "2026-02-02_kdt-backendj-21th",
  "language_quality": {},
  "concept_clarity_metrics": {},
  "interaction_metrics": {}
}
```

## LLM output (`data/outputs/llm/*_summary.json`)

```json
{
  "llm_aggregated_analysis": {
    "summary_scores": {},
    "overall_strengths": [],
    "overall_issues": [],
    "overall_evidences": []
  }
}
```

## Integrated output (`data/outputs/integrated/*_analysis.json`)

```json
{
  "lecture_id": "2026-02-02_kdt-backendj-21th",
  "metadata": {},
  "analysis": {
    "language_quality": {},
    "concept_clarity_metrics": {},
    "interaction_metrics": {},
    "summary_scores": {},
    "overall_strengths": [],
    "overall_issues": [],
    "overall_evidences": []
  }
}
```
