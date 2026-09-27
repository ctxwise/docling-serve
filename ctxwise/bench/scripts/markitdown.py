"""MarkItDown (optionally with its OCR plugin and gpt-5-mini) on the benchmark pages or the Office fixtures.
Runs in docker/markitdown.Dockerfile with bench/data at /data and test/fixtures at /fixtures;
--ocr needs OPENAI_API_KEY.
usage: python markitdown.py [--ocr] [--office]
  pages  -> /data/pred/markitdown[-ocr]/<page>.md (each image wrapped in a PDF, as a chat upload would be)
  office -> /data/office/markitdown[-ocr]-rich.<ext>.md"""

import argparse
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf
from markitdown import MarkItDown

args = argparse.ArgumentParser()
args.add_argument("--ocr", action="store_true")
args.add_argument("--office", action="store_true")
args = args.parse_args()
name = "markitdown-ocr" if args.ocr else "markitdown"
usage = {"calls": 0, "in": 0, "out": 0}

if args.ocr:
    from openai import OpenAI

    client, lock = OpenAI(), threading.Lock()
    create = client.chat.completions.create

    def counted(*a, **k):  # count LLM calls and tokens
        r = create(*a, **k)
        with lock:
            usage["calls"] += 1
            if r.usage:
                usage["in"] += r.usage.prompt_tokens
                usage["out"] += r.usage.completion_tokens
        return r

    client.chat.completions.create = counted
    md = MarkItDown(enable_plugins=True, llm_client=client, llm_model="gpt-5-mini", keep_data_uris=args.office)
else:
    md = MarkItDown(keep_data_uris=args.office)


def page(img):
    out = f"/data/pred/{name}/{os.path.splitext(img)[0]}.md"
    if os.path.exists(out):
        return 0
    t = time.time()
    pdf = f"/tmp/{os.path.splitext(img)[0]}.pdf"
    Path(pdf).write_bytes(pymupdf.open(f"/data/OmniDocBench/images/{img}").convert_to_pdf())
    try:
        text = md.convert(pdf).text_content
    except Exception as e:
        text = ""
        print("FAIL", img, repr(e)[:200], flush=True)
    Path(out).write_text(text, encoding="utf-8")
    return time.time() - t


if args.office:
    os.makedirs("/data/office", exist_ok=True)
    for ext in ["docx", "pptx", "xlsx"]:
        Path(f"/data/office/{name}-rich.{ext}.md").write_text(
            md.convert(f"/fixtures/rich.{ext}").text_content, encoding="utf-8"
        )
else:
    os.makedirs(f"/data/pred/{name}", exist_ok=True)
    imgs = [n for n in Path("/data/hard.txt").read_text(encoding="utf-8").splitlines() if n]
    t0 = time.time()
    with ThreadPoolExecutor(6) as ex:
        times = sorted(ex.map(page, imgs))
    print(f"{len(imgs)} pages in {time.time() - t0:.0f}s, median {times[len(times) // 2]:.1f}s/page", flush=True)
print(f"LLM calls {usage['calls']}, tokens in {usage['in']} out {usage['out']}", flush=True)
