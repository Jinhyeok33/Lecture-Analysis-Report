# Runbook

## 1) Prepare inputs

1. Place transcript(s) in `data/raw/`.
2. Place metadata CSV in `data/metadata/lecture_metadata.csv`.

## 2) Run pipeline

Full pipeline:

```bash
python -m src.pipeline.run_pipeline --transcript data/raw/<lecture>.txt --metadata data/metadata/lecture_metadata.csv
```

NLP + integrate + report (with existing LLM output):

```bash
python -m src.pipeline.run_pipeline \
  --run-nlp --run-integrate --run-report \
  --transcript data/raw/<lecture>.txt \
  --llm-json data/outputs/llm/<lecture>_summary.json \
  --metadata data/metadata/lecture_metadata.csv \
  --strict
```

## 3) Validate outputs only

```bash
python -m src.pipeline.run_pipeline \
  --validate-only \
  --nlp-json data/outputs/nlp/<file>.json \
  --llm-json data/outputs/llm/<file>.json \
  --analysis-json data/outputs/integrated/<file>.json \
  --metadata data/metadata/lecture_metadata.csv \
  --strict
```

## 4) Output locations

- NLP: `data/outputs/nlp`
- LLM: `data/outputs/llm`
- Integrated JSON: `data/outputs/integrated`
- PDF: `data/outputs/reports`
