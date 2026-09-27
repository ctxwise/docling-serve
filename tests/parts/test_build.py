"""Parts: identical output to the reference TypeScript implementation, plus the routing rules."""

import copy
import hashlib
import json
from pathlib import Path

from docling_serve.parts.build import build_parts, page_blocks, page_text, to_blocks

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = json.loads((FIXTURES / "golden.json").read_text(encoding="utf-8"))


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["document"][
        "json_content"
    ]


def comparable(parts: list[dict]) -> list[dict]:
    """Image payloads as hashes, like the golden file."""
    out = []
    for p in parts:
        if p["type"] == "image":  # "page" is new here: not in the reference output
            p = {k: v for k, v in p.items() if k not in ("data", "page")} | {
                "data_sha1": hashlib.sha1(p["data"].encode()).hexdigest()
            }
        out.append(p)
    return out


PAPER = load("docling-paper.json")
WITH_PAGE_IMAGES = copy.deepcopy(PAPER)
for page in WITH_PAGE_IMAGES["pages"].values():
    page["image"] = {"uri": "data:image/png;base64,AAAA"}


def test_blocks_match_reference():
    assert comparable(to_blocks(PAPER)) == GOLDEN["paper_default"]
    assert comparable(to_blocks(PAPER, max_images=1)) == GOLDEN["paper_max1"]
    assert comparable(to_blocks(PAPER, picture_text_chars=0)) == GOLDEN["paper_notext"]


def test_office_blocks_match_reference():
    for name in ("docx", "pptx", "xlsx"):
        assert comparable(to_blocks(load(f"rich-{name}.json"))) == GOLDEN[name], name


def test_page_text_matches_reference():
    for n, expected in GOLDEN["paper_page_text"].items():
        text, hint = page_text(PAPER, int(n))
        assert {"text": text, **({"hint": hint} if hint else {})} == expected, n


def test_page_blocks_match_reference():
    mixed = page_blocks(WITH_PAGE_IMAGES, image_pages={2}, scores={1: 0.93, 2: 0.787})
    assert comparable(mixed) == GOLDEN["paper_mixed"]
    assert (
        comparable(page_blocks(WITH_PAGE_IMAGES, max_page_images=3))
        == GOLDEN["paper_capped"]
    )


def test_routing_mixed_pages_keeps_confident_pages_as_text():
    parts = build_parts(
        WITH_PAGE_IMAGES, page_scores={1: 0.93, 2: 0.7, 3: 0.95}, score=0.7
    )
    text = "\n".join(p["text"] for p in parts if p["type"] == "text")
    assert "[page 1, confidence 0.93]" in text and "[page 2, confidence 0.70]" in text
    assert sum(p["type"] == "image" and p["data"] == "AAAA" for p in parts) == 1, (
        "only page 2 as a page image"
    )


def test_routing_all_low_sends_the_source_or_page_images():
    scores = dict.fromkeys(range(1, 10), 0.5)
    assert build_parts(WITH_PAGE_IMAGES, page_scores=scores, score=0.5) == [
        {"type": "source"}
    ]
    parts = build_parts(
        WITH_PAGE_IMAGES, page_scores=scores, score=0.5, source_readable=False
    )
    assert sum(p["type"] == "image" and p["data"] == "AAAA" for p in parts) == 9


def test_routing_images_and_empty_documents():
    photo = {  # docling converts images to PDF, so the origin says PDF
        "origin": {"mimetype": "application/pdf"},
        "pages": {"1": {}},
        "texts": [],
        "pictures": [],
        "tables": [],
    }
    for min_confidence in (0.8, 0):
        parts = build_parts(
            photo,
            page_scores={},
            score=0.0,
            is_image=True,
            min_confidence=min_confidence,
        )
        assert parts == [{"type": "source"}], "a photo is never lost"
    # page mode on an image: the original file, not docling's re-render
    photo_page = {
        **photo,
        "pages": {"1": {"image": {"uri": "data:image/png;base64,AAAA"}}},
    }
    parts = build_parts(
        photo_page, page_scores={1: 0.9}, score=0.9, is_image=True, mode="pages"
    )
    assert parts == [{"type": "source"}]


def test_routing_page_mode_and_page_cap():
    parts = build_parts(
        WITH_PAGE_IMAGES, page_scores={}, score=0.9, mode="pages", max_page_images=3
    )
    assert sum(p["type"] == "image" for p in parts) == 3
    cut = build_parts(PAPER, page_scores={}, score=0.9, max_pages=2)
    assert cut[-1]["text"].endswith(
        "[only the first 2 pages were read; the document may continue]"
    )
