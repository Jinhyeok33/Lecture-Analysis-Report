# EduInsight AI

Integrated lecture-quality analysis pipeline.

## Repository layout

- `data/raw`: raw lecture transcript files
- `data/preprocessed`: outputs from preprocessing stage
- `data/metadata`: metadata CSV files
- `data/outputs/nlp`: NLP engine outputs
- `data/outputs/llm`: LLM engine outputs
- `data/outputs/integrated`: integrated `analysis.json`
- `data/outputs/reports`: generated PDF reports
- `src/preprocessing`: preprocessing module (from `dev/hs`)
- `src/nlp_engine`: NLP engine module (from `dev/hs`)
- `src/llm_engine`: LLM engine module (from `dev/ik`)
- `src/integration`: integration module (from `dev/jinhyeok`)
- `src/reporting`: PDF report generator (from `dev/jinhyeok`)
- `src/pipeline/run_pipeline.py`: unified runner + validators

## Unified pipeline runner

Default (all stages):

```bash
python -m src.pipeline.run_pipeline --transcript data/raw/<lecture>.txt --metadata data/metadata/lecture_metadata.csv
```

Stage-specific example (NLP + integration + report using existing LLM JSON):

```bash
python -m src.pipeline.run_pipeline \
  --run-nlp --run-integrate --run-report \
  --transcript data/raw/<lecture>.txt \
  --llm-json data/outputs/llm/<lecture>_summary.json \
  --metadata data/metadata/lecture_metadata.csv \
  --strict
```

Validation-only example:

```bash
python -m src.pipeline.run_pipeline \
  --validate-only \
  --nlp-json data/outputs/nlp/<file>.json \
  --llm-json data/outputs/llm/<file>.json \
  --analysis-json data/outputs/integrated/<file>.json \
  --metadata data/metadata/lecture_metadata.csv \
  --strict
```

## Notes

- `--run-llm` and `--run-preprocess` require `OPENAI_API_KEY`.
- Runner performs schema and artifact checks after stage execution.
