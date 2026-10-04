# Benchmarks

Inputs, outputs and scores go to `ctxwise/bench/data/` (git-ignored). Run commands from the repository root with the
server up (see [../README.md](../README.md)); scripts read `DOCLING_API_KEY`, and `DOCLING_URL`
(default `http://127.0.0.1:5001`).

| Script | Measures | Cost |
|---|---|---|
| `api_bench.py <fixtures dir>` | time and response size of `POST /v1/convert/file/parts` per file | free |
| `parts_to_markdown.py <input dir> <output dir> docling` | Markdown per document from the parts, for public benchmarks | free |
| `parts_to_markdown.py <input dir> <output dir> hybrid` | the same, with image parts transcribed by `gpt-5-mini` (`OPENAI_API_KEY`); `vision` transcribes every page; cached in `data/vision-cache/` | about $1 per 100 images |

## Public benchmarks

Each writes one Markdown file per document with `parts_to_markdown.py`, then runs the benchmark's own scorer.

- [opendataloader-bench](https://github.com/opendataloader-project/opendataloader-bench): 200 documents; reading
  order, tables, headings. Clone into `data/`, write to `data/opendataloader-bench/prediction/<name>/markdown/`,
  then `uv run src/evaluator.py` in that folder.
- [olmOCR-bench](https://github.com/allenai/olmocr/tree/main/olmocr/bench): 1,403 pages of unit tests: text,
  headers and footers, reading order, tables, math. Download with
  `uvx --from "huggingface_hub[hf_xet]" hf download --repo-type dataset allenai/olmOCR-bench --local-dir ctxwise/bench/data/olmOCR-bench`.
- [ParseBench](https://github.com/run-llama/ParseBench): about 2,000 enterprise pages; tables, charts, content,
  formatting, visual grounding.

Status: opendataloader-bench is scored (docling variant, 0.888 overall; see [../README.md](../README.md#quality)).
ParseBench needs a clean rerun.

## Choosing min_confidence (olmOCR-bench)

`olmocr_sweep.py` mixes the cached `docling` and `vision` outputs per page (vision below the threshold, docling
above) and scores every threshold with olmOCR-bench's scorer. Run on the 684 pages that have both outputs (all 522
arXiv math, 134 of 266 headers/footers, 13 multi-column, 13 tables, 2 old scans; about $1.50 of `gpt-5-mini`).
Scores are pass rates; "avg" is the mean of the four categories with more than two pages.

| Routing | Pages to vision | arXiv math | Headers/footers | Multi-column | Tables | avg |
|---|---:|---:|---:|---:|---:|---:|
| docling only (`min_confidence` 0) | 0% | 0.0 | 89.1 | 61.7 | 58.7 | 52.4 |
| `min_confidence` 0.8 (default) | 8% | 1.1 | 89.1 | 74.5 | 75.0 | 59.9 |
| `min_confidence` 0.9 | 32% | 11.4 | 92.6 | 74.5 | 81.5 | 65.0 |
| `min_confidence` 0.95 | 85% | 42.2 | 92.8 | 83.0 | 91.3 | 77.3 |
| vision only | 100% | 47.3 | 92.6 | 83.0 | 91.3 | 78.6 |
| formula pages + `min_confidence` 0.8 | 69% | 41.4 | 89.1 | 74.5 | 75.0 | 70.0 |
| formula pages + `min_confidence` 0.9 | 80% | 42.7 | 92.6 | 74.5 | 81.5 | 72.8 |

- docling's confidence does not see math: arXiv pages score a median 0.924 while docling's text (no LaTeX) passes 0%
  of the math tests, and the arXiv gain grows only in proportion to the pages sent.
- It does see layout and table trouble: at 0.8, 23-38% of table and multi-column pages go to vision and recover about
  half of vision's gain there.
- Raising the threshold to fix math sends most pages of every kind to vision (0.95 is 85%). Routing pages with a
  formula (`$$` or `[formula]` in docling's text) gets 41.3 of vision's 47.3 on arXiv without touching other pages.
- Small samples: 13 pages each for tables and multi-column; old scans (2 pages) are left out of "avg".

## Earlier OmniDocBench evaluation

The quality charts in [../docs/](../docs/COMPARISON.md) come from 88 hard OmniDocBench pages. What remains of that
suite: `scripts/select_pages.py` (page selection), `scripts/score.sh` + `eval.yaml` with `docker/eval.Dockerfile`
(OmniDocBench's evaluator), `scripts/pymupdf.py` and `scripts/markitdown.py` (competitors, with their Dockerfiles),
`scripts/office_checks.py`, and `charts/` (matplotlib, reading `data/`). It is being replaced by the public
benchmarks above.
