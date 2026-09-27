"""Convert a folder of documents to Markdown through POST /v1/convert/file/parts, for public benchmarks.

Variants:
  docling  text parts only - what docling itself read (free)
  hybrid   image parts (low-confidence pages, charts) transcribed by a vision model through OpenRouter,
           i.e. the text a model reading our parts ends up with (costs a little; cached on disk)

usage: python ctxwise/bench/parts_to_markdown.py <input dir> <output dir> [docling|hybrid] [workers=2]
env:   DOCLING_API_KEY, DOCLING_URL (default http://127.0.0.1:5001), OPENROUTER_API_KEY (hybrid)
"""

import hashlib
import json
import os
import re
import sys
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DOCLING_URL = os.environ.get("DOCLING_URL", "http://127.0.0.1:5001")
VISION_MODEL = os.environ.get("VISION_MODEL", "openai/gpt-5-mini")
CACHE = Path(__file__).parent / "data" / "vision-cache"
PROMPT = (
    "Convert this image to Markdown. Transcribe all text exactly, including handwriting, in natural reading order. "
    "Headings as Markdown headings, tables as Markdown tables with exact values, math as LaTeX. "
    "For charts, list every data value. Skip page headers, footers and page numbers. Output only the Markdown."
)
# lines we add as hints for the model; benchmarks score the document's own text
HINT_LINE = re.compile(
    r"^\[(page \d+|image |chart|repeated image|image not shown|only the first)[^\n]*\]$",
    re.M,
)


def post_json(url: str, body: bytes, headers: dict, timeout: int) -> dict:
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def convert(path: Path) -> dict:
    """The document's parts; page images instead of `source`, so every image can be transcribed."""
    boundary = uuid.uuid4().hex
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{path.name}"\r\n\r\n'.encode()
        + path.read_bytes()
        + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="ocr_preset"\r\n\r\nrapidocr\r\n--{boundary}--\r\n'.encode()
    )
    return post_json(
        f"{DOCLING_URL}/v1/convert/file/parts?source_readable=false",
        body,
        {
            "x-api-key": os.environ["DOCLING_API_KEY"],
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        timeout=1800,
    )


def transcribe(media_type: str, data: str) -> str:
    """A vision model's Markdown for one image, cached by content."""
    cached = CACHE / f"{hashlib.sha256(data.encode()).hexdigest()}.md"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    body = {
        "model": VISION_MODEL,
        "reasoning": {"effort": "low"},
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
        "https://openrouter.ai/api/v1/chat/completions",
        json.dumps(body).encode(),
        {
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
            "Content-Type": "application/json",
        },
        timeout=300,
    )
    text = re.sub(
        r"^```(?:markdown)?\n|\n```$",
        "",
        result["choices"][0]["message"]["content"].strip(),
    )
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8")
    return text


def to_markdown(parts: list[dict], variant: str) -> str:
    blocks = []
    for part in parts:
        if part["type"] == "text":
            blocks.append(HINT_LINE.sub("", part["text"]).strip())
        elif part["type"] == "image" and variant == "hybrid":
            blocks.append(transcribe(part["media_type"], part["data"]))
    return "\n\n".join(b for b in blocks if b) + "\n"


def run(path: Path, out_dir: Path, variant: str) -> None:
    target = out_dir / f"{path.stem}.md"
    if target.exists():
        return  # resumable
    try:
        target.write_text(
            to_markdown(convert(path)["parts"], variant), encoding="utf-8"
        )
    except Exception as error:
        print(f"FAIL {path.name}: {str(error)[:200]}", file=sys.stderr, flush=True)


def main() -> None:
    in_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    variant = sys.argv[3] if len(sys.argv) > 3 else "docling"
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 2
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in in_dir.iterdir() if p.is_file())
    with ThreadPoolExecutor(workers) as pool:
        for i, _ in enumerate(pool.map(lambda p: run(p, out_dir, variant), files), 1):
            if i % 10 == 0:
                print(f"{i}/{len(files)}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
