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
- `src/preprocessing`: preprocessing module (to be integrated from `dev/hs`)
- `src/nlp_engine`: NLP engine module (to be integrated from `dev/hs`)
- `src/llm_engine`: LLM engine module (to be integrated from `dev/ik`)
- `src/integration`: integration module (migrated from `dev/jinhyeok`)
- `src/reporting`: PDF report generator (migrated from `dev/jinhyeok`)
- `src/pipeline/run_pipeline.py`: single-command pipeline runner

## Current stage

This branch establishes the target repository schema and migrates `dev/jinhyeok` modules first.

## Run (integration + report)

```bash
python -m src.pipeline.run_pipeline \
  --nlp data/outputs/nlp/sample_nlp.json \
  --llm data/outputs/llm/sample_summary.json \
  --metadata data/metadata/lecture_metadata.csv \
  --analysis-out data/outputs/integrated/sample_analysis.json \
  --report-out data/outputs/reports/sample_report.pdf
```
