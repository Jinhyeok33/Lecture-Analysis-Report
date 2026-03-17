#!/bin/bash

set -e

echo "=== NLP engine batch start ==="
python -m src.nlp_engine data/raw
echo "=== NLP engine batch done ==="
