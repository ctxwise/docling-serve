#!/usr/bin/env bash
# Scores data/pred/<method> against the hard-page ground truth with OmniDocBench's evaluator
# (text edit distance, reading order, table TEDS; CDM skipped - it needs TeX Live).
# Results: bench/data/results/<method>_quick_match_*.json
# usage (repo root): bash bench/scripts/score.sh <method>...
set -euo pipefail
data="$(cd "$(dirname "$0")/../data" && pwd -W 2>/dev/null || pwd)"
for method in "$@"; do
  [ -d "bench/data/pred/$method" ] || { echo "no bench/data/pred/$method" >&2; exit 1; }
  sed "s#{method}#$method#" bench/scripts/eval.yaml > "bench/data/results/$method.yaml"
  MSYS_NO_PATHCONV=1 docker run --rm -v "$data:/data" -v "$data/results:/evalkit/result" omnidocbench-eval \
    python pdf_validation.py --config "/data/results/$method.yaml" > "bench/data/results/$method.log" 2>&1
  python -c "
import json
r = json.load(open('bench/data/results/${method}_quick_match_metric_result.json'))
print(f\"$method: text {r['text_block']['page']['Edit_dist']['ALL']:.3f}  reading order {r['reading_order']['page']['Edit_dist']['ALL']:.3f}  TEDS {r['table']['all']['TEDS']['all'] * 100:.1f}\")"
done
