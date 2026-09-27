"""Pick the benchmark pages from OmniDocBench: a stratified sample (by data source), then its hard pages.
Writes data/hard.txt (image names) and data/hard_gt.json (ground truth for the evaluator).
usage: python bench/scripts/select_pages.py"""

import collections
import json
import random
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
SAMPLE, SEED = 120, 0
HARD_SOURCES = {"note", "exam_paper", "colorful_textbook", "historical_document", "newspaper"}

gt = json.loads((DATA / "OmniDocBench/OmniDocBench.json").read_text(encoding="utf-8"))
by_source = collections.defaultdict(list)
for page in gt:
    by_source[page["page_info"]["page_attribute"]["data_source"]].append(page)
rng = random.Random(SEED)
sample = [p for group in by_source.values() for p in rng.sample(group, max(2, round(SAMPLE * len(group) / len(gt))))]


def hard(page):
    attr = page["page_info"]["page_attribute"]
    return (
        attr["data_source"] in HARD_SOURCES
        or attr["layout"] == "other_layout"
        or any(b["category_type"] == "table" for b in page["layout_dets"])
    )


pages = [p for p in sample if hard(p)]
(DATA / "hard_gt.json").write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
(DATA / "hard.txt").write_text("\n".join(p["page_info"]["image_path"] for p in pages), encoding="utf-8")
print(
    len(pages), "hard pages:", dict(collections.Counter(p["page_info"]["page_attribute"]["data_source"] for p in pages))
)
