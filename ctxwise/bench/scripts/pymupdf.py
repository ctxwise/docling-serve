"""PyMuPDF4LLM on the benchmark pages (each image wrapped in a PDF) or on the Office fixtures.
Runs in docker/pymupdf.Dockerfile with bench/data at /data and test/fixtures at /fixtures (see bench/README.md).
usage: python pymupdf.py [--ocr tesseract|rapidocr] [--office]
  pages  -> /data/pred/pymupdf-<ocr>/<page>.md
  office -> /data/office/pymupdf4llm-rich.<ext>.md"""

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pymupdf
import pymupdf4llm

args = argparse.ArgumentParser()
args.add_argument("--ocr", choices=["tesseract", "rapidocr"], default="rapidocr")
args.add_argument("--office", action="store_true")
args = args.parse_args()
OUT = f"/data/pred/pymupdf-{args.ocr}"


def to_markdown(doc):
    if args.ocr == "rapidocr":  # the same OCR engine as docling
        from pymupdf4llm.ocr.rapidocr_api import exec_ocr

        return pymupdf4llm.to_markdown(doc, ocr_function=exec_ocr)
    return pymupdf4llm.to_markdown(doc)  # default: Tesseract, English only


def page(img):
    out = f"{OUT}/{os.path.splitext(img)[0]}.md"
    if os.path.exists(out):
        return 0
    t = time.time()
    try:
        md = to_markdown(pymupdf.open("pdf", pymupdf.open(f"/data/OmniDocBench/images/{img}").convert_to_pdf()))
    except Exception as e:
        md = ""
        print("FAIL", img, e, flush=True)
    Path(out).write_text(md, encoding="utf-8")
    return time.time() - t


if args.office:
    os.makedirs("/data/office", exist_ok=True)
    for ext in ["docx", "pptx", "xlsx"]:
        Path(f"/data/office/pymupdf4llm-rich.{ext}.md").write_text(
            pymupdf4llm.to_markdown(f"/fixtures/rich.{ext}"), encoding="utf-8"
        )
else:
    os.makedirs(OUT, exist_ok=True)
    imgs = [n for n in Path("/data/hard.txt").read_text(encoding="utf-8").splitlines() if n]
    t0 = time.time()
    with ProcessPoolExecutor(4) as ex:
        times = sorted(ex.map(page, imgs))
    print(f"{len(imgs)} pages in {time.time() - t0:.0f}s; median {times[len(times) // 2]:.1f}s/page", flush=True)
