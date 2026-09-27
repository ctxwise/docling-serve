"""README charts: the middleware's modes on the hard pages, thresholds, speed and memory."""

import os
import re
from pathlib import Path

from matplotlib.colors import LinearSegmentedColormap
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
    per_page,
    plt,
    teds,
    text,
    title,
)

MODES = [  # label, method, input tokens/page, recommended default
    ("Docling text only", "docling", 1073, False),
    ("Page image only", "vision", 3635, False),
    ("Docling + low-confidence\nfallback (default)", "default", 2222, True),
    ("Page mode\n(image + dense-page hint)", "pages", 3810, False),
]
M = {k: metric(k) for _, k, _, _ in MODES}
names, picks = [m[0] for m in MODES], [m[3] for m in MODES]
os.makedirs(OUT, exist_ok=True)

# 1. quality: three metrics as small multiples (separate scales, never a dual axis)
fig, axes = plt.subplots(1, 3, figsize=(12, 3.4), sharey=True)
for ax, (lab, f, fmt, xmax) in zip(
    axes,
    [
        ("Text error  (lower is better)", text, "{:.3f}", 0.22),
        ("Reading-order error  (lower is better)", order, "{:.3f}", 0.42),
        ("Table accuracy, TEDS  (higher is better)", teds, "{:.1f}", 100),
    ],
    strict=True,
):
    hbars(ax, names, [f(M[k]) for _, k, _, _ in MODES], picks, fmt, xmax, lab)
title(
    fig,
    "Parsing quality on hard pages",
    "OmniDocBench, 88 hard pages (handwriting, tables, charts, irregular layouts, newspapers), gpt-5-mini",
)
fig.savefig(f"{OUT}/quality.png")
plt.close(fig)

# 2. heatmap: text error by page type x mode
cats = [*PAGE_TYPES, ("All hard pages", "ALL")]
fig, ax = plt.subplots(figsize=(9.5, 4.6))
im = heatmap(
    ax,
    [[text(M[k], g) for _, k, _, _ in MODES] for _, g in cats],
    names,
    [c[0] for c in cats],
    LinearSegmentedColormap.from_list("blues", BLUES),
    vmax=0.55,
)
cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
cb.outline.set_visible(False)
cb.ax.tick_params(colors=MUTED, labelsize=8)
cb.set_label("text error (lower is better)", color=INK2, fontsize=8.5)
title(
    fig,
    "Where each approach fails",
    "Text error by page type; bold = best in the row. "
    "Vision wins on handwriting and layouts; dense print needs docling text",
)
fig.savefig(f"{OUT}/by-page-type.png")
plt.close(fig)

# 3. lines: confidence threshold sweep (two panels, own axes)
doc, page = per_page("docling"), per_page("pages")
conf = confidence()
imgs = [i for i in doc if i in page and i in conf]
ts = [round(0.66 + 0.01 * i, 2) for i in range(26)]
err = [sum(page[i] if conf[i] < t else doc[i] for i in imgs) / len(imgs) for t in ts]
share = [100 * sum(conf[i] < t for i in imgs) / len(imgs) for t in ts]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 3.4))
for ax, ys, lab, fmt in [
    (a1, err, "Text error (lower is better)", "{:.3f}"),
    (a2, share, "Pages sent as images (%)", "{:.0f}%"),
]:
    ax.plot(ts, ys, color=ACC, lw=2, solid_capstyle="round", zorder=3)
    i8 = ts.index(0.8)
    ax.scatter([0.8], [ys[i8]], s=40, color=ACC, edgecolor=SURF, linewidth=2, zorder=4)
    ax.annotate(
        f"default 0.8: {fmt.format(ys[i8])}",
        (0.8, ys[i8]),
        xytext=(-10, 12),
        textcoords="offset points",
        fontsize=9,
        fontweight="bold",
        ha="right",
    )
    ax.axvline(0.8, color=GRID, lw=1, zorder=1)
    ax.set_title(lab, fontsize=10, loc="left", pad=8)
    ax.set_xlabel("minConfidence (docling low_score)")
    ax.yaxis.grid(True, color=GRID, lw=0.6, zorder=0)
a1.axhline(text(M["pages"]), color=GRAY, lw=1, ls="--")
a1.text(0.665, text(M["pages"]) - 0.006, "page mode on every page", color=INK2, fontsize=8.5, va="top")
title(
    fig,
    "Choosing the low-confidence threshold",
    "Pages below the threshold go to the model as images. 0.8 reaches page-mode accuracy with 40% of pages as images",
)
fig.savefig(f"{OUT}/confidence-threshold.png")
plt.close(fig)

# 4. line: dense-page hint threshold (page mode), same rule as the middleware: hint only above N chars and no table
hyb, vis = per_page("hybrid"), per_page("vision")
chars, table = {}, {}
for i in vis:
    p = f"{DATA}/pred/docling/{os.path.splitext(i)[0]}.md"
    md = Path(p).read_text(encoding="utf-8") if os.path.exists(p) else ""
    chars[i], table[i] = len(md), bool(re.search(r"^\|.*\|\s*$", md, re.M))
ks = [i for i in vis if i in hyb]
th = list(range(0, 10001, 250))
e2 = [sum(hyb[i] if chars[i] > t and not table[i] else vis[i] for i in ks) / len(ks) for t in th]
fig, ax = plt.subplots(figsize=(8, 3.3))
ax.plot(th, e2, color=ACC, lw=2, zorder=3)
ax.axvspan(2500, 6000, color=BLUES[0], alpha=0.5, zorder=0, lw=0)
ax.text(4250, max(e2) * 0.98, "flat region 2,500-6,000", ha="center", fontsize=8.5, color=INK2, va="top")
ax.scatter([3000], [e2[th.index(3000)]], s=40, color=ACC, edgecolor=SURF, linewidth=2, zorder=4)
ax.annotate(
    f"default 3,000 chars: {e2[th.index(3000)]:.3f}",
    (3000, e2[th.index(3000)]),
    xytext=(10, 10),
    textcoords="offset points",
    fontsize=9,
    fontweight="bold",
)
ax.set_xlabel("add docling text as a hint when a page has more than N characters")
ax.set_ylabel("text error")
ax.yaxis.grid(True, color=GRID, lw=0.6, zorder=0)
ax.text(0, e2[0] + 0.004, "hint on every page", fontsize=8.5, color=INK2, va="bottom")
ax.text(10000, e2[-1], "never  ", fontsize=8.5, color=INK2, va="bottom", ha="right")
title(
    fig,
    "Choosing the dense-page hint threshold (page mode)",
    "Docling text is added as a hint on pages above N characters without a table; "
    "vision alone misreads dense small print",
)
fig.savefig(f"{OUT}/hint-threshold.png")
plt.close(fig)

# 5. scatter: cost vs quality (label offsets placed by hand so no label covers a point)
fig, ax = plt.subplots(figsize=(7.5, 4))
place = {
    "docling": (10, -3, "left"),
    "vision": (-10, 8, "right"),
    "default": (0, 16, "center"),
    "pages": (-10, -22, "right"),
}
for name, k, tok, pick in MODES:
    e = text(M[k])
    ax.scatter(tok, e, s=90 if pick else 60, color=ACC if pick else GRAY, edgecolor=SURF, linewidth=2, zorder=3)
    dx, dy, ha = place[k]
    ax.annotate(
        name if k == "pages" else name.replace("\n", " "),
        (tok, e),
        xytext=(dx, dy),
        textcoords="offset points",
        va="center",
        fontsize=9,
        fontweight="bold" if pick else "normal",
        color=INK if pick else INK2,
        ha=ha,
    )
ax.set_xlim(0, 4400)
ax.set_ylim(0, 0.2)
ax.set_xlabel("input tokens per page")
ax.set_ylabel("text error (lower is better)")
ax.grid(True, color=GRID, lw=0.6, zorder=0)
title(fig, "Cost vs quality", "Bottom-left is best. The default keeps page-mode accuracy at ~58% of its token cost")
fig.savefig(f"{OUT}/cost-vs-quality.png")
plt.close(fig)

# 6. speed by server size: seconds per page and response size,
#    every page rendered up front vs only the pages that need it (two panels)
runs = [(lab, f"{DATA}/speed-{k}.json") for lab, k in [("4 vCPU / 16 GB", "4vcpu"), ("2 vCPU / 8 GB", "2vcpu")]]
runs = [(lab, load_json(p)) for lab, p in runs if os.path.exists(p)]
if runs:
    rows = [
        (f"{'9-page paper' if f.startswith('docling') else '2-page scan'}\n{lab}", d[f]) for lab, d in runs for f in d
    ]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 1.4 + 0.75 * len(rows)), sharey=True)
    y = list(range(len(rows)))[::-1]
    for ax, key, fmt, lab in [
        (a1, "sec_page", "{:.1f}s", "seconds per page (lower is better)"),
        (a2, "mb", "{:.1f} MB", "response size (lower is better)"),
    ]:

        def get(r, v, key=key):
            return r[v]["seconds"] / r["pages"] if key == "sec_page" else r[v]["mb"]

        b = [get(r, "all-pages") for _, r in rows]
        a = [get(r, "on-demand") for _, r in rows]
        top = max(b + a) * 1.3
        ax.barh([v + 0.19 for v in y], b, height=0.36, color=GRAY, zorder=2, label="every page rendered")
        ax.barh([v - 0.19 for v in y], a, height=0.36, color=ACC, zorder=2, label="only as needed (current)")
        for yi, bv, av in zip(y, b, a, strict=True):
            ax.text(bv + top * 0.01, yi + 0.19, fmt.format(bv), va="center", fontsize=8.5, color=INK2)
            ax.text(
                av + top * 0.01,
                yi - 0.19,
                f"{fmt.format(av)}  ({(av - bv) / bv * 100:+.0f}%)",
                va="center",
                fontsize=8.5,
                fontweight="bold",
            )
        ax.set_xlim(0, top)
        ax.set_title(lab, fontsize=10, loc="left", pad=8)
        ax.xaxis.grid(True, color=GRID, lw=0.6, zorder=0)
        ax.tick_params(axis="y", length=0)
    a1.set_yticks(y, [r[0] for r in rows])
    a2.legend(frameon=False, loc="lower right", fontsize=9)
    title(
        fig,
        "Docling speed by server size",
        "Container limited to the listed vCPUs and RAM; median of 3 runs after warm-up. "
        "Rendering page images only when needed",
    )
    fig.savefig(f"{OUT}/speed.png")
    plt.close(fig)

# 7. memory: peak container memory per phase, per server size
mem = []
for lab, k in [("4 vCPU / 16 GB, 2 workers", "4vcpu"), ("2 vCPU / 8 GB, 1 worker", "2vcpu")]:
    sp, pp = f"{DATA}/mem-{k}-samples.csv", f"{DATA}/mem-{k}-phases.json"
    if os.path.exists(sp) and os.path.exists(pp):
        samples = [tuple(map(float, line.split(","))) for line in Path(sp).read_text().split("\n")[1:] if line]
        ph = load_json(pp)

        def peak(s, e, samples=samples):
            return max([m for t, m in samples if s - 1 <= t <= e + 1] or [0]) / 1024

        mem.append(
            (
                lab,
                {
                    "Idle": peak(ph[0]["start"], ph[0]["end"]),
                    "1 PDF (9 pages)": peak(ph[1]["start"], ph[1]["end"]),
                    "4 documents at once": peak(ph[3]["start"], ph[3]["end"]),
                    "Legacy .doc + .xls\n(LibreOffice)": peak(ph[5]["start"], ph[5]["end"]),
                },
            )
        )
if mem:
    cats = list(mem[0][1])
    fig, ax = plt.subplots(figsize=(9, 3.6))
    w = 0.36
    for n, (lab, d) in enumerate(mem):
        xs = [i + (n - 0.5) * w for i in range(len(cats))]
        vals = [d[c] for c in cats]
        ax.bar(xs, vals, width=w * 0.92, color=ACC if n == 0 else GRAY, label=lab, zorder=2)
        for x, v in zip(xs, vals, strict=True):
            ax.text(
                x,
                v + 0.06,
                f"{v:.1f}",
                ha="center",
                fontsize=8.5,
                fontweight="bold" if n == 0 else "normal",
                color=INK if n == 0 else INK2,
            )
    ax.set_xticks(range(len(cats)), cats)
    ax.tick_params(axis="x", length=0, colors=INK2)
    ax.set_ylabel("peak memory (GiB)")
    ax.set_ylim(0, max(max(d.values()) for _, d in mem) * 1.25)
    ax.yaxis.grid(True, color=GRID, lw=0.6, zorder=0)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    title(
        fig,
        "docling-serve memory",
        "Container memory sampled every ~3 s; peak per phase. Both sizes stay well under their RAM",
    )
    fig.savefig(f"{OUT}/memory.png")
    plt.close(fig)
print("written:", sorted(f for f in os.listdir(OUT) if not f.startswith("compare-")))
