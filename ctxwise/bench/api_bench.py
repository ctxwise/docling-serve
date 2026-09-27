"""API benchmark (free, no LLM calls): time and payload of POST /v1/convert/file/parts per file.

Needs a running server and DOCLING_API_KEY.
usage: python ctxwise/bench/api_bench.py <fixtures dir> [runs=2] > results.json
"""

import base64
import json
import os
import statistics
import struct
import sys
import time
import urllib.request
import uuid
from pathlib import Path

URL = os.environ.get("DOCLING_URL", "http://127.0.0.1:5001")
KEY = os.environ["DOCLING_API_KEY"]
FILES = [
    "scan.pdf",
    "mixed.pdf",
    "docling-paper.pdf",
    "newspaper.jpg",
    "report.docx",
    "rich.pptx",
    "rich.xlsx",
    "legacy-table.doc",
]


def multipart(file: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{file.name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    )
    return head.encode() + file.read_bytes() + f"\r\n--{boundary}--\r\n".encode(), (
        f"multipart/form-data; boundary={boundary}"
    )


def image_info(part: dict) -> dict:
    raw = base64.b64decode(part["data"][:48])
    px = struct.unpack(">II", raw[16:24]) if raw[:8] == b"\x89PNG\r\n\x1a\n" else None
    kb = round(len(part["data"]) * 3 / 4 / 1024)
    return {
        "kb": kb,
        "px": px,
        "format": part["media_type"],
        "class": part.get("picture_class"),
    }


def run(file: Path) -> dict:
    body, content_type = multipart(file)
    request = urllib.request.Request(
        f"{URL}/v1/convert/file/parts",
        data=body,
        headers={"x-api-key": KEY, "Content-Type": content_type},
    )
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=1800) as response:
        raw = response.read()
    wall = time.perf_counter() - start
    result = json.loads(raw)
    processing = result.get("processing_time") or 0
    return {
        "wall_s": round(wall, 2),
        "processing_s": round(processing, 2),
        "overhead_s": round(wall - processing, 2),
        "response_kb": round(len(raw) / 1024),
        "text_chars": sum(
            len(p["text"]) for p in result["parts"] if p["type"] == "text"
        ),
        "images": [image_info(p) for p in result["parts"] if p["type"] == "image"],
        "source_parts": sum(p["type"] == "source" for p in result["parts"]),
        "confidence": result["confidence"],
    }


def main() -> None:
    fixtures = Path(sys.argv[1])
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    run(fixtures / "scan.pdf")  # warm-up: models load on first use
    results = {}
    for name in FILES:
        samples = [run(fixtures / name) for _ in range(runs)]
        medians = {
            k: statistics.median(s[k] for s in samples)
            for k in ("wall_s", "processing_s", "overhead_s")
        }
        results[name] = {**samples[-1], **medians}
        print(
            f"{name:20s} wall {medians['wall_s']:6.1f}s  processing {medians['processing_s']:6.1f}s  "
            f"overhead {medians['overhead_s']:4.1f}s  response {samples[-1]['response_kb']:6} KB",
            file=sys.stderr,
        )
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
