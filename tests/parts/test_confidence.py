"""Per-page confidence on conversion results."""

import math

from docling.datamodel.base_models import ConfidenceReport, PageConfidenceScores
from docling.datamodel.service.responses import ConfidenceScores

from docling_serve.parts.confidence import enable_page_confidence, page_scores


def report() -> ConfidenceReport:
    scores = ConfidenceReport()
    scores.pages = {
        1: PageConfidenceScores(parse_score=0.9, layout_score=0.7),
        2: PageConfidenceScores(parse_score=0.95, layout_score=0.95),
        3: PageConfidenceScores(),  # nothing scored: NaN
    }
    return scores


def test_from_scores_carries_page_scores():
    enable_page_confidence()
    scores = ConfidenceScores.from_scores(report())
    assert set(scores.pages) == {1, 2}  # NaN page skipped
    assert all(
        isinstance(s, float) and not math.isnan(s) for s in scores.pages.values()
    )
    assert scores.pages[1] < scores.pages[2]


def test_enable_page_confidence_is_idempotent():
    enable_page_confidence()
    enable_page_confidence()
    assert set(ConfidenceScores.from_scores(report()).pages) == {1, 2}


def test_page_scores_uses_pages_and_their_minimum():
    enable_page_confidence()
    scores = ConfidenceScores.from_scores(report())
    pages, low = page_scores(scores)
    assert pages == scores.pages
    assert low == min(scores.pages.values())


def test_page_scores_falls_back_to_the_document_score():
    assert page_scores(ConfidenceScores(low_score=0.4)) == ({}, 0.4)


def test_page_scores_without_confidence():
    assert page_scores(None) == ({}, None)
