# Architecture

## End-to-end flow

1. Preprocessing (`src/preprocessing`)
2. NLP analysis (`src/nlp_engine`)
3. LLM analysis (`src/llm_engine`)
4. Result integration (`src/integration/result_integrator.py`)
5. PDF generation (`src/reporting/report_generator.py`)

## Data contracts

- NLP output: `lecture_id`, `language_quality`, `concept_clarity_metrics`, `interaction_metrics`
- LLM output: `llm_aggregated_analysis.summary_scores`, `overall_strengths`, `overall_issues`, `overall_evidences`
- Integrated output: `lecture_id`, `metadata`, `analysis`
