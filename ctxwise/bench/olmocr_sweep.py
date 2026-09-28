"""Lay out olmOCR-bench candidates for a min_confidence sweep, from the cached docling and vision runs.

Each olmOCR-bench PDF is one page, so a threshold picks per document: the vision transcription when docling's
confidence is below it, docling's text otherwise (what the parts endpoint routes). Threshold 0 is docling alone,
1.01 is vision alone. Needs staging/docling and staging/vision from parts_to_markdown.py (docling / vision
variants). Only documents with both outputs are scored: data/olmOCR-bench/sweep/ gets those PDFs, their tests,
one candidate folder per threshold, and scores.csv (document, category, confidence).

usage: python ctxwise/bench/olmocr_sweep.py
then:  docker run --rm -v <repo>/ctxwise/bench/data/olmOCR-bench/sweep:/data olmocr-score --skip_baseline
"""

import csv
import hashlib
import json
import shutil
from pathlib import Path

DATA = Path(__file__).parent / "data"
BENCH = DATA / "olmOCR-bench"
THRESHOLDS = [0, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.925, 0.95, 0.975, 1.01]


def confidence(pdf: Path) -> float:
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    cached = DATA / "parts-cache" / f"{sha}-docling.json"
    return json.loads(cached.read_text(encoding="utf-8"))["confidence"]


def main() -> None:
    pdfs, out = BENCH / "bench_data" / "pdfs", BENCH / "sweep"
    shutil.rmtree(out, ignore_errors=True)
    docs = []
    for pdf in sorted(pdfs.rglob("*.pdf")):
        rel = pdf.relative_to(pdfs)
        docling = BENCH / "staging" / "docling" / rel.with_suffix(".md")
        vision = BENCH / "staging" / "vision" / rel.with_suffix(".md")
        if docling.exists() and vision.exists():
            docs.append((rel, confidence(pdf), docling, vision))
            (out / "pdfs" / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pdf, out / "pdfs" / rel)
    kept = {rel.as_posix() for rel, *_ in docs}
    for tests in (BENCH / "bench_data").glob("*.jsonl"):
        lines = tests.read_text(encoding="utf-8").splitlines()
        subset = [line for line in lines if json.loads(line)["pdf"] in kept]
        if subset:
            (out / tests.name).write_text("\n".join(subset) + "\n", encoding="utf-8")
    with open(out / "scores.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(
            [("document", "category", "confidence")]
            + [(rel.as_posix(), rel.parts[0], score) for rel, score, *_ in docs]
        )
    print(f"{len(docs)} documents with both outputs")
    for t in THRESHOLDS:
        for rel, score, docling, vision in docs:
            target = out / f"sweep_{t:.3f}" / rel.parent / f"{rel.stem}_pg1_repeat1.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(vision if score < t else docling, target)
        share = sum(score < t for _, score, *_ in docs) / len(docs)
        print(f"sweep_{t:.3f}: {share:6.1%} of pages to vision")


if __name__ == "__main__":
    main()
