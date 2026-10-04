"""Convert a folder of documents to Markdown through POST /v1/convert/file/parts, for public benchmarks.

Variants:
  docling  docling's text for every page (min_confidence=0): docling on its own (free)
  hybrid   our routing: docling's text where it is confident, low-confidence pages and pictures as images,
           transcribed by a vision model: the text a model reading our parts ends up with
  vision   every page as an image, transcribed (mode=pages): the vision-only baseline

Conversions are cached per document and variant in data/parts-cache/, transcriptions in data/vision-cache/,
so re-runs are free. Input folders are walked recursively; the output mirrors their layout.

usage: python ctxwise/bench/parts_to_markdown.py <input dir> <output dir> [docling|hybrid] [workers=2]
env:   DOCLING_API_KEY, DOCLING_URL (default http://127.0.0.1:5001), OPENAI_API_KEY (hybrid, vision),
       MAX_TRANSCRIPTIONS (spending cap: vision calls attempted per run, default 2000),
       DOCLING_OPTIONS (extra docling options, e.g. "pdf_backend=pypdfium2,table_mode=fast")
"""

import hashlib
import json
import os
import re
import sys
import threading
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DOCLING_URL = os.environ.get("DOCLING_URL", "http://127.0.0.1:5001")
VISION_MODEL = os.environ.get("VISION_MODEL", "gpt-5-mini")
DATA = Path(__file__).parent / "data"
MAX_TRANSCRIPTIONS = int(os.environ.get("MAX_TRANSCRIPTIONS", "2000"))
# extra docling-serve form fields, e.g. DOCLING_OPTIONS="pdf_backend=pypdfium2" (part of the cache key)
DOCLING_OPTIONS = dict(
    pair.split("=", 1)
    for pair in os.environ.get("DOCLING_OPTIONS", "").split(",")
    if "=" in pair
)
transcriptions = 0
budget_lock = threading.Lock()
PROMPT = (
    "Convert this image to Markdown. Transcribe all text exactly, including handwriting, in natural reading order. "
    "Headings as Markdown headings, tables as Markdown tables with exact values, math as LaTeX. "
    "For charts, list every data value. Skip page headers, footers and page numbers. Output only the Markdown."
)
# Marker lines we add for the model. Benchmarks score the document's own text, so a picture marker is reduced to
# its caption (document text) and page/cut markers are dropped.
PICTURE_MARKER = re.compile(
    r"^\[(?:image \d+|image not shown|chart|repeated image)(?: \([^)]*\))?(?:: (?P<caption>.*?))?"
    r"(?: \| text in image: .*)?\]$",
    re.M,
)
OTHER_MARKER = re.compile(r"^\[(?:page \d+[^\]]*|only the first [^\]]*)\]$", re.M)
QUERY = {
    "docling": "min_confidence=0&source_readable=false",
    "hybrid": "source_readable=false",
    "vision": "mode=pages&source_readable=false",
}


def post_json(url: str, body: bytes, headers: dict, timeout: int) -> dict:
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def convert(path: Path, variant: str) -> dict:
    """The document's parts; page images instead of `source`, so every image can be transcribed."""
    content = path.read_bytes()
    name = f"{hashlib.sha256(content).hexdigest()}-{variant}"
    if DOCLING_OPTIONS:
        name += (
            "-" + hashlib.sha256(json.dumps(DOCLING_OPTIONS).encode()).hexdigest()[:8]
        )
    cached = DATA / "parts-cache" / f"{name}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    boundary = uuid.uuid4().hex
    fields = {"ocr_preset": "rapidocr", **DOCLING_OPTIONS}
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{path.name}"\r\n\r\n'.encode()
        + content
        + b"".join(
            f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}'.encode()
            for k, v in fields.items()
        )
        + f"\r\n--{boundary}--\r\n".encode()
    )
    result = post_json(
        f"{DOCLING_URL}/v1/convert/file/parts?{QUERY[variant]}",
        body,
        {
            "x-api-key": os.environ["DOCLING_API_KEY"],
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        timeout=1800,
    )
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(result), encoding="utf-8")
    return result


def transcribe(media_type: str, data: str) -> str:
    """A vision model's Markdown for one image, cached by content."""
    global transcriptions
    cached = DATA / "vision-cache" / f"{hashlib.sha256(data.encode()).hexdigest()}.md"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    with budget_lock:
        if transcriptions >= MAX_TRANSCRIPTIONS:
            raise RuntimeError(f"MAX_TRANSCRIPTIONS={MAX_TRANSCRIPTIONS} reached")
        transcriptions += 1
    body = {
        "model": VISION_MODEL,
        "reasoning_effort": "low",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{data}"},
                    },
                ],
            }
        ],
    }
    result = post_json(
        "https://api.openai.com/v1/chat/completions",
        json.dumps(body).encode(),
        {
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        timeout=300,
    )
    text = re.sub(
        r"^```(?:markdown)?\n|\n```$",
        "",
        result["choices"][0]["message"]["content"].strip(),
    )
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8")
    return text


def to_markdown(parts: list[dict], variant: str) -> str:
    blocks = []
    for part in parts:
        if part["type"] == "text":
            text = PICTURE_MARKER.sub(lambda m: m["caption"] or "", part["text"])
            blocks.append(OTHER_MARKER.sub("", text).strip())
        elif part["type"] == "image" and variant != "docling":
            blocks.append(transcribe(part["media_type"], part["data"]))
    return "\n\n".join(b for b in blocks if b) + "\n"


def run(path: Path, in_dir: Path, out_dir: Path, variant: str) -> None:
    target = (out_dir / path.relative_to(in_dir)).with_suffix(".md")
    if target.exists():
        return  # resumable
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(
            to_markdown(convert(path, variant)["parts"], variant), encoding="utf-8"
        )
    except Exception as error:
        print(f"FAIL {path.name}: {str(error)[:200]}", file=sys.stderr, flush=True)


def main() -> None:
    in_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    variant = sys.argv[3] if len(sys.argv) > 3 else "docling"
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(
        p for p in in_dir.rglob("*") if p.is_file() and not p.name.startswith(".")
    )
    with ThreadPoolExecutor(workers) as pool:
        for i, _ in enumerate(
            pool.map(lambda p: run(p, in_dir, out_dir, variant), files), 1
        ):
            if i % 10 == 0:
                print(f"{i}/{len(files)}", file=sys.stderr, flush=True)
    print(
        f"done: {len(files)} documents, {transcriptions} vision calls attempted",
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":
    main()
