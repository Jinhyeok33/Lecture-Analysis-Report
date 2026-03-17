# LLM Engine

Batch processor for lecture transcript analysis using OpenAI.

## Run

From repository root:

```bash
python -m src.llm_engine.entrypoints.batch_processor \
  --input data/raw \
  --output data/outputs/llm
```

## Options

- `--input`, `-i`: transcript directory (`*.txt`), default `data/raw`
- `--output`, `-o`: output directory, default `data/outputs/llm`
- `--file`, `-f`: process a single file
- `--latest`, `-l`: process only the latest transcript in input directory
- `--max_concurrency`, `-c`: concurrent chunk workers

## Output files

- `{lecture_id}_chunks.json`
- `{lecture_id}_summary.json`
