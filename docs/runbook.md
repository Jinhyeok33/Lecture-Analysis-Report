# Runbook

1. Put metadata CSV into `data/metadata/`.
2. Place NLP JSON output into `data/outputs/nlp/`.
3. Place LLM JSON output into `data/outputs/llm/`.
4. Run:

```bash
python -m src.pipeline.run_pipeline --nlp <NLP_JSON> --llm <LLM_JSON> --metadata <CSV> --analysis-out <ANALYSIS_JSON> --report-out <PDF>
```
