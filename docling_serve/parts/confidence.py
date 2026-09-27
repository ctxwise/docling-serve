"""Per-page confidence on conversion results.

docling scores every page, but docling-serve's result model keeps only the document score
("A per-page breakdown can be added later as an optional ``pages`` field"). This adds that field.
It lives on the in-memory result, so it reaches the /parts result endpoint with the local orchestrator;
with serialized result stores (Redis, Ray) the document score is used instead.
"""

import math

from docling.datamodel.service.responses import ConfidenceScores


class PageConfidenceScores(ConfidenceScores):
    """Document scores plus each page's low_score (page number -> 0-1)."""

    pages: dict[int, float] = {}


_document_scores = ConfidenceScores.from_scores


def _with_pages(scores) -> ConfidenceScores:
    pages = {
        int(n): s.low_score
        for n, s in (getattr(scores, "pages", None) or {}).items()
        if isinstance(s.low_score, float) and not math.isnan(s.low_score)
    }
    return PageConfidenceScores(**_document_scores(scores).model_dump(), pages=pages)


def enable_page_confidence() -> None:
    """Make every conversion result carry per-page scores. Safe to call more than once."""
    ConfidenceScores.from_scores = staticmethod(_with_pages)  # type: ignore[method-assign]


def page_scores(
    confidence: ConfidenceScores | None,
) -> tuple[dict[int, float], float | None]:
    """(page number -> score, worst score) from a result's confidence."""
    pages = getattr(confidence, "pages", None) or {}
    if pages:
        return pages, min(pages.values())
    return {}, confidence.low_score if confidence else None
