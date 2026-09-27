"""Scores the Office outputs in data/office/<parser>-rich.<ext>.md against 21 checks -> data/office-checks.json.
Outputs come from office.ts (this project), markitdown.py --office and pymupdf.py --office.
usage: python bench/scripts/office_checks.py"""

import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
PARSERS = {
    "This project": "docling",
    "MarkItDown + OCR": "markitdown-ocr",
    "MarkItDown": "markitdown",
    "PyMuPDF4LLM": "pymupdf4llm",
}
PICTURE = "PICTURE"
CHECKS = [
    ("docx", "Word: heading", r"Quarterly Report"),
    ("docx", "Word: nested bullet", r"Sub point"),
    ("docx", "Word: numbered list", r"Step two"),
    ("docx", "Word: table cell", r"2\.1M"),
    ("docx", "Word: merged header", r"2026"),
    ("docx", "Word: picture (image or description)", PICTURE),
    ("docx", "Word: caption", r"Figure 1"),
    ("docx", "Word: page header", r"ACME Corp"),
    ("docx", "Word: page footer", r"Confidential"),
    ("pptx", "PowerPoint: slide title", r"Roadmap 2026"),
    ("pptx", "PowerPoint: nested bullet", r"Detail b"),
    ("pptx", "PowerPoint: table", r"\bGA\b"),
    ("pptx", "PowerPoint: speaker notes", r"Speaker note"),
    ("pptx", "PowerPoint: chart values", r"North[^\n]{0,20}42"),
    ("pptx", "PowerPoint: picture (image or description)", PICTURE),
    ("xlsx", "Excel: sheet 1 table", r"EU"),
    ("xlsx", "Excel: sheet 2", r"Figures in USD"),
    ("xlsx", "Excel: sheet names", r"Sheet: Sales|## Sales"),
    ("xlsx", "Excel: merged header", r"2026"),
    ("xlsx", "Excel: date", r"2026-03-31"),
    ("xlsx", "Excel: chart", r"Revenue chart"),
]


def has_picture(text, parser):
    """a real image the model receives, or an LLM-written description; a file name alone doesn't count"""
    if parser == "docling":
        return "![image part](image/" in text
    embedded = re.search(r"data:image/[a-z]+;base64,[A-Za-z0-9+/]{100}", text)
    described = any(len(alt) > 40 for alt in re.findall(r"!\[([^\]]*)\]", text))
    return bool(embedded or described)


rows = []
for ext, label, pattern in CHECKS:
    results = {}
    for name, parser in PARSERS.items():
        f = DATA / "office" / f"{parser}-rich.{ext}.md"
        text = f.read_text(encoding="utf-8") if f.exists() else ""
        results[name] = has_picture(text, parser) if pattern == PICTURE else bool(re.search(pattern, text))
    rows.append({"label": label, "results": results})
(DATA / "office-checks.json").write_text(json.dumps({"parsers": list(PARSERS), "rows": rows}, indent=1))
for name in PARSERS:
    print(f"{name:18s} {sum(r['results'][name] for r in rows)}/{len(rows)}")
