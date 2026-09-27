# Benchmarks

Inputs, outputs and scores go to `ctxwise/bench/data/` (git-ignored). Run commands from the repository root with the
server up (see [../README.md](../README.md)); scripts read `DOCLING_API_KEY`, and `DOCLING_URL`
(default `http://127.0.0.1:5001`).

| Script | Measures | Cost |
|---|---|---|
| `api_bench.py <fixtures dir>` | time and response size of `POST /v1/convert/file/parts` per file | free |
| `parts_to_markdown.py <input dir> <output dir> docling` | Markdown per document from the parts, for public benchmarks | free |
| `parts_to_markdown.py <input dir> <output dir> hybrid` | the same, with image parts transcribed by `openai/gpt-5-mini` via OpenRouter (`OPENROUTER_API_KEY`); cached in `data/vision-cache/` | about $1 per 100 images |

## Public benchmarks

Each writes one Markdown file per document with `parts_to_markdown.py`, then runs the benchmark's own scorer.

- [opendataloader-bench](https://github.com/opendataloader-project/opendataloader-bench) - 200 documents; reading
  order, tables, headings. Clone into `data/`, write to `data/opendataloader-bench/prediction/<name>/markdown/`,
  then `uv run src/evaluator.py` in that folder.
- [olmOCR-bench](https://github.com/allenai/olmocr/tree/main/olmocr/bench) - 1,403 pages of unit tests: text,
  headers and footers, reading order, tables, math. Download with
  `uvx --from "huggingface_hub[hf_xet]" hf download --repo-type dataset allenai/olmOCR-bench --local-dir ctxwise/bench/data/olmOCR-bench`.
- [ParseBench](https://github.com/run-llama/ParseBench) - about 2,000 enterprise pages; tables, charts, content,
  formatting, visual grounding.

Status: opendataloader-bench is scored (docling variant, 0.888 overall; see [../README.md](../README.md#quality)).
olmOCR-bench and ParseBench runs were interrupted and need a clean rerun; every hybrid run needs OpenRouter
credit. Conversions and transcriptions are cached, so reruns only pay for what is missing.

## Earlier OmniDocBench evaluation

The quality charts in [../docs/](../docs/COMPARISON.md) come from 88 hard OmniDocBench pages. What remains of that
suite: `scripts/select_pages.py` (page selection), `scripts/score.sh` + `eval.yaml` with `docker/eval.Dockerfile`
(OmniDocBench's evaluator), `scripts/pymupdf.py` and `scripts/markitdown.py` (competitors, with their Dockerfiles),
`scripts/office_checks.py`, and `charts/` (matplotlib, reading `data/`). It is being replaced by the public
benchmarks above.
