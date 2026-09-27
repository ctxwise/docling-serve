"""Turn a converted document into LLM-ready parts: compact text plus only the images worth sending.

Works on the DoclingDocument JSON (``export_to_dict()``). The rules were measured on OmniDocBench hard pages:
docling's text where docling is confident, the page image where it isn't, pictures as images with their
caption and inner text.
"""

import hashlib
import re
from typing import Any

Doc = dict[str, Any]
Part = dict[str, Any]

# picture classes (docling figure classifier) that carry information the model must read precisely
INFO_CLASSES = {
    "bar_chart",
    "line_chart",
    "pie_chart",
    "scatter_plot",
    "box_plot",
    "flow_chart",
    "table",
    "engineering_drawing",
    "chemistry_structure",
    "geographical_map",
    "topographical_map",
    "screenshot_from_computer",
    "screenshot_from_manual",
}
# pictures where inner OCR text is noise and fine detail matters least
PHOTO_CLASSES = {"photograph", "signature", "stamp"}


def fmt_score(score: float) -> str:
    """Round down, so 0.796 reads 0.79 and never looks like it passed a 0.8 threshold."""
    return f"{int(score * 100) / 100:.2f}"


def _data_uri(uri: str | None) -> tuple[str, str] | None:
    """'data:image/png;base64,...' -> (media type, base64 payload)."""
    if not uri or not uri.startswith("data:"):
        return None
    return uri[5 : uri.index(";")], uri[uri.index(",") + 1 :]


def _clean(text: str | None) -> str:
    # U+FFFF = a ligature docling could not map; collapse runs of spaces
    return re.sub(r"[ \t]+", " ", (text or "").replace("\uffff", "\ufffd")).strip()


def _page_of(item: dict | None) -> int | None:
    prov = (item or {}).get("prov") or []
    return prov[0].get("page_no") if prov else None


def to_blocks(  # noqa: C901 - one walk over the document, kept together on purpose
    doc: Doc,
    *,
    page: int | None = None,
    max_images: int = 10,
    skip_classes: frozenset[str] = frozenset({"logo", "icon"}),
    min_image_px: int = 48,
    picture_text_chars: int = 600,
) -> list[Part]:
    """The document (or one page of it) in reading order: Markdown text parts and image parts."""
    out: list[Part] = []
    seen: set[str] = set()
    shown = 0

    def get(ref: str) -> dict | None:
        _, kind, i = ref.split("/")  # "#/texts/12"
        items = doc.get(kind) or []
        return items[int(i)] if int(i) < len(items) else None

    def on_page(item: dict | None) -> bool:
        return not page or _page_of(item) == page

    def caption_of(item: dict) -> str:
        return " ".join(
            t
            for c in item.get("captions") or []
            if (t := _clean((get(c["$ref"]) or {}).get("text")))
        )

    def push(text: str) -> None:
        if not text:
            return
        if out and out[-1]["type"] == "text":
            out[-1]["text"] += f"\n\n{text}"
        else:
            out.append({"type": "text", "text": text})

    def table(item: dict) -> str:
        grid = (item.get("data") or {}).get("grid") or []
        if not grid:
            return ""

        # leading header rows (spanning headers repeat per column) -> one header row "group / sub";
        # a row counts as header when most of its filled cells are flagged (the corner cell often isn't)
        def is_header(row: list[dict]) -> bool:
            filled = [c for c in row if c.get("text")]
            return bool(filled) and sum(
                1 for c in filled if c.get("column_header")
            ) * 2 >= len(filled)

        h = 0
        while h < len(grid) - 1 and is_header(grid[h]):
            h += 1
        h = max(h, 1)
        cols = len(grid[0])
        head = [
            " / ".join(
                dict.fromkeys(
                    t
                    for r in grid[:h]
                    if c < len(r) and (t := _clean(r[c].get("text")))
                )
            )
            for c in range(cols)
        ]

        def row(cells: list[str]) -> str:
            return (
                "|"
                + "|".join(c.replace("|", "\\|").replace("\n", " ") for c in cells)
                + "|"
            )

        lines = [
            row(head),
            "|" + "-|" * cols,
            *(row([_clean(c.get("text")) for c in r]) for r in grid[h:]),
        ]
        cap = caption_of(item)
        return (f"{cap}\n" if cap else "") + "\n".join(lines)

    def list_text(group: dict, depth: int) -> str:
        lines = []
        for i, child in enumerate(group.get("children") or []):
            item = get(child["$ref"])
            if not item or item.get("content_layer") != "body":
                continue
            if item.get("label") in ("list", "ordered_list"):
                lines.append(list_text(item, depth + 1))
                continue
            if not on_page(item):
                continue
            bullet = f"{i + 1}." if item.get("enumerated") else "-"
            nested = [
                k
                for c in item.get("children") or []
                if (k := get(c["$ref"])) and k.get("label") == "list"
            ]
            lines.append(
                "\n".join(
                    [
                        f"{'  ' * depth}{bullet} {_clean(item.get('text'))}",
                        *(list_text(k, depth + 1) for k in nested),
                    ]
                )
            )
        return "\n".join(line for line in lines if line)

    def class_of(pic: dict) -> str | None:
        predictions = (
            ((pic.get("meta") or {}).get("classification") or {}).get("predictions")
        ) or []
        return predictions[0].get("class_name") if predictions else None

    def b64_of(pic: dict) -> str:
        data = _data_uri((pic.get("image") or {}).get("uri"))
        return data[1] if data else ""

    def sendable(pic: dict) -> bool:
        size = (pic.get("image") or {}).get("size")
        cls = class_of(pic)
        too_small = bool(size) and (
            size["width"] < min_image_px or size["height"] < min_image_px
        )
        return (
            pic.get("content_layer") == "body"
            and on_page(pic)
            and bool(b64_of(pic))
            and cls not in skip_classes
            and not too_small
        )

    caption_refs = {
        c["$ref"]
        for x in [*(doc.get("pictures") or []), *(doc.get("tables") or [])]
        for c in x.get("captions") or []
    }

    # which pictures fit under max_images: charts, diagrams and tables first, photos last, bigger first
    def rank(pic: dict) -> tuple[int, float]:
        cls = class_of(pic)
        size = (pic.get("image") or {}).get("size") or {}
        return (
            0 if cls in INFO_CLASSES else 2 if cls in PHOTO_CLASSES else 1,
            -size.get("width", 0) * size.get("height", 0),
        )

    hashes: set[str] = set()
    unique = []
    for pic in doc.get("pictures") or []:
        if (
            sendable(pic)
            and (h := hashlib.sha1(b64_of(pic).encode()).hexdigest()) not in hashes
        ):
            hashes.add(h)
            unique.append(pic)
    chosen = {p["self_ref"] for p in sorted(unique, key=rank)[:max_images]}

    def picture(pic: dict) -> None:
        nonlocal shown
        cls = class_of(pic)
        if cls in skip_classes:
            return  # decorative: nothing worth saying either
        cap = caption_of(pic)
        desc = (f" ({cls.replace('_', ' ')})" if cls else "") + (
            f": {cap}" if cap else ""
        )
        # text docling read inside the picture (axis labels, values); capped, never for photos
        caption_ids = {k["$ref"] for k in pic.get("captions") or []}
        inner = " | ".join(
            t
            for c in pic.get("children") or []
            if c["$ref"] not in caption_ids
            and (t := _clean((get(c["$ref"]) or {}).get("text")))
        )
        if len(inner) > picture_text_chars:
            inner = (
                re.sub(r"\s*\|?\s*\S*$", "", inner[:picture_text_chars], count=1)
                + " ..."
            )
        inner_note = (
            f" | text in image: {inner}"
            if inner and picture_text_chars > 0 and cls not in PHOTO_CLASSES
            else ""
        )
        b64 = b64_of(pic)
        # charts stored as data (PowerPoint, Excel): docling reads the values -> an exact table
        chart_data = ((pic.get("meta") or {}).get("tabular_chart") or {}).get(
            "chart_data"
        )
        chart = (
            table({"data": chart_data}) if chart_data and chart_data.get("grid") else ""
        )
        if not b64 and chart:
            return push(f"[chart{desc}]\n{chart}")
        digest = hashlib.sha1(b64.encode()).hexdigest() if b64 else ""
        if digest and digest in seen:
            return push(f"[repeated image{desc}]")
        chart_suffix = f"\n{chart}" if chart else ""
        if pic["self_ref"] not in chosen:
            return push(f"[image not shown{desc}{inner_note}]{chart_suffix}")
        if digest:
            seen.add(digest)
        shown += 1
        push(f"[image {shown}{desc}{inner_note}]{chart_suffix}")
        part: Part = {
            "type": "image",
            "media_type": (pic.get("image") or {}).get("mimetype") or "image/png",
            "data": b64,
        }
        if cls:
            part["picture_class"] = cls
        out.append(part)

    def walk(ref: str) -> None:  # noqa: C901
        item = get(ref)
        if not item:
            return
        layer = item.get("content_layer")
        if layer == "notes":  # PowerPoint speaker notes
            return push(f"Notes: {_clean(item.get('text'))}")
        if layer != "body":  # furniture: page headers and footers
            return
        kind = ref.split("/")[1]
        if kind != "groups" and not on_page(item):
            return
        if kind == "pictures":
            return picture(
                item
            )  # its children are its caption and the text inside the image
        if kind == "tables":
            return push(table(item))
        label = item.get("label")
        if kind == "groups":
            # sheet names (Excel) and slide numbers (PowerPoint), so the model can refer to them
            if label == "sheet" and item.get("name"):
                push(f"## Sheet: {_clean(item['name'])}")
            if label == "chapter" and (
                slide := re.fullmatch(r"slide-(\d+)", item.get("name") or "")
            ):
                push(f"[slide {int(slide[1]) + 1}]")
            if label in ("list", "ordered_list"):
                return push(list_text(item, 0))
            if label == "inline":
                children = [get(c["$ref"]) for c in item.get("children") or []]
                return push(
                    " ".join(
                        _clean((c or {}).get("text")) for c in children if on_page(c)
                    )
                )
            for child in item.get("children") or []:
                walk(child["$ref"])
            return
        if ref in caption_refs:  # printed with its picture or table already
            return
        text = _clean(item.get("text"))
        if label == "title":
            push(f"# {text}")
        elif label == "section_header":
            push(f"{'#' * min((item.get('level') or 1) + 1, 6)} {text}")
        elif label == "code":
            push(f"```\n{(item.get('text') or '').strip()}\n```")
        elif label == "formula":
            push(f"$${text}$$" if text else "[formula]")
        elif label == "list_item":
            push(f"- {text}")
        else:
            push(text)
        for child in item.get("children") or []:
            walk(child["$ref"])

    # Word page header/footer (e.g. "Confidential") once; in PDFs furniture is per-page noise, so skipped
    if not page and re.search(
        r"wordprocessingml|msword", (doc.get("origin") or {}).get("mimetype") or ""
    ):
        furniture = [
            t
            for x in doc.get("texts") or []
            if x.get("content_layer") == "furniture" and (t := _clean(x.get("text")))
        ]
        if furniture:
            push(f"Page header/footer: {' | '.join(dict.fromkeys(furniture))}")
    for child in (doc.get("body") or {}).get("children") or []:
        walk(child["$ref"])
    return out


def page_text(
    doc: Doc, page: int, dense_chars: int = 3000, **options: Any
) -> tuple[str, str | None]:
    """A page's docling text, and the hint to send next to its image (dense pages without tables only).

    Measured: the image alone wins on handwriting, tables and layout, but vision misreads dense small print.
    """
    text = "\n".join(
        p["text"]
        for p in to_blocks(doc, **{**options, "page": page, "max_images": 0})
        if p["type"] == "text"
    )
    has_table = any(
        t.get("content_layer") == "body" and _page_of(t) == page
        for t in doc.get("tables") or []
    )
    hint = None
    if len(text) > dense_chars and not has_table:
        hint = (
            "Text extracted by a layout parser (reading order may be wrong; the image is the ground truth):\n"
            f"<parser>\n{text}\n</parser>"
        )
    return text, hint


def page_blocks(
    doc: Doc,
    *,
    image_pages: set[int] | None = None,
    scores: dict[int, float] | None = None,
    source: bool = False,
    dense_chars: int = 3000,
    max_page_images: int = 20,
    **options: Any,
) -> list[Part]:
    """Page by page: image pages as the rendered page (+ a dense-page hint), other pages as docling text.

    ``source`` marks where the original file should go instead of docling's render (single images).
    """
    nums = sorted(int(n) for n in doc.get("pages") or {})
    if not nums and source:
        return [{"type": "source"}]
    out: list[Part] = []
    images = 0
    for n in nums:
        if len(nums) > 1:
            score = (scores or {}).get(n)
            out.append(
                {
                    "type": "text",
                    "text": f"[page {n}"
                    + (
                        f", confidence {fmt_score(score)}]"
                        if score is not None
                        else "]"
                    ),
                }
            )
        if image_pages is not None and n not in image_pages:
            out += to_blocks(doc, page=n, **options)
            continue
        text, hint = page_text(doc, n, dense_chars, **options)
        render = _data_uri(
            ((doc["pages"].get(str(n)) or {}).get("image") or {}).get("uri")
        )
        if images >= max_page_images or not (source or render):
            if text:
                out.append(
                    {"type": "text", "text": text}
                )  # docling's text is all the model gets
            continue
        images += 1
        if hint:
            out.append({"type": "text", "text": hint})
        out.append(
            {"type": "source"}
            if source
            else {
                "type": "image",
                "media_type": render[0],
                "data": render[1],
                "page": n,
            }
        )
    return out


def merge_text(parts: list[Part]) -> list[Part]:
    """Adjacent text parts joined, so the client sends fewer parts."""
    merged: list[Part] = []
    for part in parts:
        if part["type"] == "text" and merged and merged[-1]["type"] == "text":
            merged[-1] = {
                **merged[-1],
                "text": merged[-1]["text"] + "\n" + part["text"],
            }
        else:
            merged.append(part)
    return merged


def build_parts(
    doc: Doc,
    *,
    page_scores: dict[int, float],
    score: float | None,
    is_image: bool = False,
    mode: str = "docling",
    source_readable: bool = True,
    min_confidence: float = 0.8,
    max_pages: int = 100,
    dense_chars: int = 3000,
    max_page_images: int = 20,
    **options: Any,
) -> list[Part]:
    """Route one converted document.

    mode "docling": docling's text and pictures; pages below ``min_confidence`` as page images.
    mode "pages": every page as an image, plus docling's text on dense pages.
    ``source_readable``: the client's model reads the original file, so a ``source`` part may replace renders.
    ``is_image``: the upload was an image (docling converts images to PDF, so the document can't tell).
    """
    mimetype = (doc.get("origin") or {}).get("mimetype") or ""
    is_pdf = not is_image and mimetype == "application/pdf"
    pages = mode == "pages"
    fallback = not pages and (is_pdf or is_image) and min_confidence > 0
    low = {n for n, s in page_scores.items() if s < min_confidence}
    empty = not (doc.get("texts") or doc.get("pictures") or doc.get("tables"))

    per_page = {
        "dense_chars": dense_chars,
        "max_page_images": max_page_images,
        **options,
    }
    parts: list[Part] | None = None
    if fallback and not is_image and low and len(low) < len(page_scores):
        # some pages low: docling's text for the confident pages, page images only for the low ones
        parts = page_blocks(doc, image_pages=low, scores=page_scores, **per_page)
    elif (fallback and (score if score is not None else 1) < min_confidence) or (
        empty and (is_image or is_pdf)
    ):
        # low confidence, or nothing extracted: the model reads the original (a PDF: its own text layer + pages)
        if source_readable and not is_image:
            return [{"type": "source"}]
        pages = True
    if parts is None:
        parts = (
            page_blocks(doc, source=is_image and source_readable, **per_page)
            if pages
            else to_blocks(doc, **options)
        )
    if not is_image and len(doc.get("pages") or {}) >= max_pages:
        parts.append(
            {
                "type": "text",
                "text": f"[only the first {max_pages} pages were read; the document may continue]",
            }
        )
    return merge_text(parts)
