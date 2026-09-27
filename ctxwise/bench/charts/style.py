"""Shared chart style and data access. The charts run in the eval image:
docker run --rm -v "<bench>:/bench" -v "<docs/images>:/images" omnidocbench-eval python /bench/charts/<chart>.py"""

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATA, OUT = "/bench/data", "/images"
# palette (light): accent blue, de-emphasis gray, orange; chrome + ink
ACC, GRAY, ORG = "#2a78d6", "#c3c2b7", "#eb6834"
INK, INK2, MUTED, GRID, AXIS, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]  # sequential ramp
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "text.color": INK,
        "axes.labelcolor": INK2,
        "axes.edgecolor": AXIS,
        "xtick.color": MUTED,
        "ytick.color": INK2,
        "axes.facecolor": SURF,
        "figure.facecolor": SURF,
        "savefig.facecolor": SURF,
        "axes.grid": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.25,
    }
)

# OmniDocBench page groups shown in the heatmaps
PAGE_TYPES = [
    ("Handwritten notes", "data_source: note"),
    ("Exam papers", "data_source: exam_paper"),
    ("Colorful textbooks", "data_source: colorful_textbook"),
    ("Irregular layouts", "layout: other_layout"),
    ("Newspapers", "data_source: newspaper"),
    ("Academic papers", "data_source: academic_literature"),
]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def metric(method):
    return load_json(f"{DATA}/results/{method}_quick_match_metric_result.json")


def per_page(method):
    return load_json(f"{DATA}/results/{method}_quick_match_text_block_per_page_edit.json")


def confidence():
    """docling's confidence (low_score) per benchmark page, from data/docling-json"""
    folder = f"{DATA}/docling-json"
    return {f[:-5]: load_json(f"{folder}/{f}")["confidence"]["low_score"] for f in os.listdir(folder)}


def text(m, group="ALL"):
    return m["text_block"]["page"]["Edit_dist"].get(group)


def order(m, group="ALL"):
    return m["reading_order"]["page"]["Edit_dist"].get(group)


def teds(m):
    return m["table"]["all"]["TEDS"]["all"] * 100


def title(fig, t, sub):
    fig.text(0.01, 1.04, t, fontsize=13, fontweight="bold", ha="left")
    fig.text(0.01, 0.985, sub, fontsize=9.5, color=INK2, ha="left")


def hbars(ax, labels, values, picks, fmt, xmax, title_=None):
    """horizontal bars, the picked ones in the accent color and bold"""
    y = list(range(len(values)))[::-1]
    ax.barh(y, values, height=0.55, color=[ACC if p else GRAY for p in picks], zorder=2)
    ax.set_yticks(y, labels)
    for yi, v, p in zip(y, values, picks, strict=True):
        ax.text(v + xmax * 0.015, yi, fmt.format(v), va="center", fontsize=9, fontweight="bold" if p else "normal")
    ax.set_xlim(0, xmax)
    ax.xaxis.grid(True, color=GRID, lw=0.6, zorder=0)
    ax.tick_params(axis="y", length=0)
    if title_:
        ax.set_title(title_, fontsize=10, loc="left", color=INK, pad=8)


def heatmap(ax, data, xlabels, ylabels, cmap, vmax, fmt="{:.2f}", best=min):
    """cell values printed; the best of each row in bold"""
    im = ax.imshow([[v if v is not None else 0 for v in r] for r in data], cmap=cmap, vmin=0, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(xlabels)), xlabels, fontsize=8.5)
    ax.set_yticks(range(len(ylabels)), ylabels)
    for i, row in enumerate(data):
        top = best(v for v in row if v is not None)
        for j, v in enumerate(row):
            ax.text(
                j,
                i,
                "-" if v is None else fmt.format(v),
                ha="center",
                va="center",
                fontsize=9,
                color="white" if (v or 0) > vmax * 0.55 else INK,
                fontweight="bold" if v == top else "normal",
            )
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.set_xticks([x - 0.5 for x in range(1, len(xlabels))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(ylabels))], minor=True)
    ax.grid(which="minor", color=SURF, lw=2)
    ax.tick_params(which="minor", length=0)
    return im
