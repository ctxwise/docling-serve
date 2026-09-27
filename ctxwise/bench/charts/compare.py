"""docs/COMPARISON.md charts: this project vs docling alone vs PyMuPDF4LLM vs MarkItDown + OCR plugin."""

import os

from matplotlib.colors import LinearSegmentedColormap, ListedColormap
from style import (
    ACC,
    BLUES,
    DATA,
    GRAY,
    GRID,
    INK,
    INK2,
    MUTED,
    OUT,
    PAGE_TYPES,
    SURF,
    confidence,
    hbars,
    heatmap,
    load_json,
    metric,
    order,
    plt,
    teds,
    text,
    title,
)

PARSERS = [  # label, method, share of pages sent to an LLM for reading, pick
    ("This project\n(docling + gpt-5-mini fallback)", "default", None, True),
    ("docling alone", "docling", 0.0, False),
    ("PyMuPDF4LLM\n(RapidOCR)", "pymupdf-rapidocr", 0.0, False),
    ("MarkItDown + OCR plugin\n(gpt-5-mini)", "markitdown-ocr", 1.0, False),
]
PARSERS = [p for p in PARSERS if os.path.exists(f"{DATA}/results/{p[1]}_quick_match_metric_result.json")]
R = {k: metric(k) for _, k, _, _ in PARSERS}
names, picks = [p[0] for p in PARSERS], [p[3] for p in PARSERS]

# 1. overall: three metrics as small multiples
fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.6), sharey=True)
for ax, (lab, f, fmt, xmax) in zip(
    axes,
    [
        ("Text error  (lower is better)", text, "{:.3f}", 0.9),
        ("Reading-order error  (lower is better)", order, "{:.3f}", 0.7),
        ("Table accuracy, TEDS  (higher is better)", teds, "{:.1f}", 100),
    ],
    strict=True,
):
    hbars(ax, names, [f(R[k]) for _, k, _, _ in PARSERS], picks, fmt, xmax, lab)
title(
    fig,
    "Parsing quality: four approaches on the same 88 hard pages",
    "OmniDocBench hard pages (handwriting, tables, charts, irregular layouts, newspapers; English and Chinese)",
)
fig.savefig(f"{OUT}/compare-quality.png")
plt.close(fig)

# 2/3. heatmaps by page type
cats = [
    *PAGE_TYPES,
    ("Research reports", "data_source: research_report"),
    ("English pages", "language: english"),
    ("Chinese pages", "language: simplified_chinese"),
    ("All 88 pages", "ALL"),
]
cmap = LinearSegmentedColormap.from_list("blues", BLUES)
for fname, f, lab in [
    ("compare-heatmap-text.png", text, "text error"),
    ("compare-heatmap-reading.png", order, "reading-order error"),
]:
    fig, ax = plt.subplots(figsize=(10, 5.6))
    heatmap(ax, [[f(R[k], g) for _, k, _, _ in PARSERS] for _, g in cats], names, [c[0] for c in cats], cmap, vmax=1.0)
    title(
        fig,
        f"{lab.capitalize()} by page type (lower is better)",
        "Bold = best in the row. 0 = perfect, 1 = nothing right",
    )
    fig.savefig(f"{OUT}/{fname}")
    plt.close(fig)

# 4. Office features (data/office-checks.json, from scripts/office_checks.py)
oc = f"{DATA}/office-checks.json"
if os.path.exists(oc):
    checks = load_json(oc)
    parsers, rows = checks["parsers"], checks["rows"]
    grid = [[1 if r["results"][p] else 0 for p in parsers] for r in rows]
    fig, ax = plt.subplots(figsize=(7.5, 0.34 * len(rows) + 1.4))
    ax.imshow(grid, cmap=ListedColormap(["#f0efec", ACC]), vmin=0, vmax=1, aspect="auto")
    for i, r in enumerate(grid):
        for j, v in enumerate(r):
            ax.text(
                j,
                i,
                "yes" if v else "no",
                ha="center",
                va="center",
                fontsize=8.5,
                color="white" if v else MUTED,
                fontweight="bold" if v else "normal",
            )
    ax.set_xticks(range(len(parsers)), parsers, fontsize=9)
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(rows)), [r["label"] for r in rows], fontsize=8.5)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.set_xticks([x - 0.5 for x in range(1, len(parsers))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(rows))], minor=True)
    ax.grid(which="minor", color=SURF, lw=2)
    ax.tick_params(which="minor", length=0)
    totals = " · ".join(f"{p}: {sum(1 for r in grid if r[j])}/{len(rows)}" for j, p in enumerate(parsers))
    title(fig, "Word, PowerPoint and Excel: what reaches the model", totals)
    fig.savefig(f"{OUT}/compare-office.png")
    plt.close(fig)

# 5. quality vs share of pages sent to an LLM (this project: pages below minConfidence 0.8)
share = {k: s for _, k, s, _ in PARSERS}
conf = confidence().values()
share["default"] = sum(c < 0.8 for c in conf) / len(conf)
fig, ax = plt.subplots(figsize=(7.5, 4))
for name, k, _, pick in PARSERS:
    ax.scatter(
        share[k] * 100,
        text(R[k]),
        s=90 if pick else 60,
        color=ACC if pick else GRAY,
        edgecolor=SURF,
        linewidth=2,
        zorder=3,
    )
    ax.annotate(
        name.replace("\n", " "),
        (share[k] * 100, text(R[k])),
        xytext=(8, 6),
        textcoords="offset points",
        fontsize=8.5,
        fontweight="bold" if pick else "normal",
        color=INK if pick else INK2,
        ha="left" if share[k] < 0.7 else "right",
    )
ax.set_xlim(-5, 110)
ax.set_ylim(0, max(text(R[k]) for _, k, _, _ in PARSERS) * 1.2)
ax.set_xlabel("pages sent to an LLM for reading (%)")
ax.set_ylabel("text error (lower is better)")
ax.grid(True, color=GRID, lw=0.6, zorder=0)
title(fig, "Quality vs LLM use", "Bottom-left is best: accurate text with few paid LLM calls")
fig.savefig(f"{OUT}/compare-llm-use.png")
plt.close(fig)
print("written:", sorted(f for f in os.listdir(OUT) if f.startswith("compare-")))
