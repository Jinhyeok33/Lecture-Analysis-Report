"""Path configuration for NLP engine within unified repository layout."""

from __future__ import annotations

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
REPO_ROOT = SRC_DIR.parent.parent

DATA_DIR = REPO_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
NLP_OUTPUT_DIR = DATA_DIR / "outputs" / "nlp"

NLP_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Backward-compatible alias for old code
OUTPUT_NLP_DIR = str(NLP_OUTPUT_DIR)
