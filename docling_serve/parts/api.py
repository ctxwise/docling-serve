"""Models and helpers for POST /v1/convert/file/parts."""

import base64
import io
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from PIL import Image
from pydantic import BaseModel, Field

from docling.datamodel.base_models import OutputFormat
from docling.datamodel.service.options import ConvertDocumentsOptions
from docling.datamodel.service.responses import DoclingTaskResult, ExportResult
from docling_core.types.doc import ImageRefMode

from docling_serve.parts.build import build_parts
from docling_serve.parts.confidence import page_scores


class PartsOptions(BaseModel):
    """How a converted document is turned into parts."""

    mode: Literal["docling", "pages"] = Field(
        "docling",
        description="docling: text and pictures, low-confidence pages as images. pages: every page as an image.",
    )
    source_readable: bool = Field(
        True,
        description="The client's model reads the original file, so a `source` part may replace page renders.",
    )
    min_confidence: float = Field(
        0.8,
        ge=0,
        le=1,
        description="Pages below this go to the model as images. 0 = off.",
    )
    max_pages: int = Field(
        100, ge=1, description="Pages converted; used to say when a document was cut."
    )
    dense_chars: int = Field(
        3000,
        ge=0,
        description="Page mode: pages with more text also get docling's text.",
    )
    max_page_images: int = Field(
        20, ge=0, description="Page images per document; later pages go as text."
    )
    max_images: int = Field(
        10,
        ge=0,
        description="Pictures per document; charts and tables first, photos last.",
    )
    skip_classes: list[str] = Field(
        ["logo", "icon"], description="Picture classes never sent."
    )
    min_image_px: int = Field(48, ge=0, description="Smaller pictures are dropped.")
    picture_text_chars: int = Field(
        600, ge=0, description="Text read inside a chart or diagram, sent next to it."
    )


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImagePart(BaseModel):
    type: Literal["image"] = "image"
    media_type: str
    data: str = Field(description="base64")
    picture_class: str | None = None
    page: int | None = Field(None, description="Set on whole-page renders.")


class SourcePart(BaseModel):
    """Send the original file here (the model reads it better than docling did)."""

    type: Literal["source"] = "source"


class PartsResult(BaseModel):
    filename: str
    confidence: float | None = Field(
        None, description="Worst page score, or the document score."
    )
    page_confidence: dict[int, float] = {}
    processing_time: float = Field(description="Seconds docling spent converting.")
    parts: list[TextPart | ImagePart | SourcePart]


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".bmp"}

# Longest side of page renders. Anthropic resizes above 1568 px; OpenAI scales to 2048 px, then to 768 px on the
# short side, so a smaller render costs the model nothing and makes the request several times smaller.
PAGE_RENDER_MAX_SIDE = 1568


def compact_page_render(part: dict) -> dict:
    """A page render as JPEG at most PAGE_RENDER_MAX_SIDE px (docling renders PNG at 2x)."""
    image = Image.open(io.BytesIO(base64.b64decode(part["data"])))
    image.thumbnail((PAGE_RENDER_MAX_SIDE, PAGE_RENDER_MAX_SIDE))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=85, optimize=True)
    data = base64.b64encode(buffer.getvalue()).decode()
    return {**part, "media_type": "image/jpeg", "data": data}


def convert_options_for(
    options: ConvertDocumentsOptions, parts: PartsOptions
) -> ConvertDocumentsOptions:
    """The request's docling options, with what building parts depends on set."""
    crops = parts.mode != "pages"  # page mode sends whole pages, so no picture crops
    return options.model_copy(
        update={
            "to_formats": [OutputFormat.JSON],
            "image_export_mode": ImageRefMode.EMBEDDED,
            "include_images": crops,
            "do_picture_classification": crops,
            # page renders are only used for page mode and low-confidence pages
            "include_page_images": parts.mode == "pages" or parts.min_confidence > 0,
            "page_range": (1, parts.max_pages),
        }
    )


def to_parts_result(
    task_result: DoclingTaskResult, options: PartsOptions
) -> PartsResult:
    result = task_result.result
    if not isinstance(result, ExportResult):
        raise HTTPException(
            status_code=400, detail="Parts need a single-document conversion."
        )
    if result.document.json_content is None:
        errors = "; ".join(e.error_message for e in result.errors) or "unknown error"
        raise HTTPException(
            status_code=422, detail=f"The document could not be converted: {errors}"
        )
    pages, score = page_scores(result.confidence)
    settings = options.model_dump()
    settings["skip_classes"] = frozenset(settings["skip_classes"])
    parts = build_parts(
        result.document.json_content.export_to_dict(),
        page_scores=pages,
        score=score,
        is_image=Path(result.document.filename).suffix.lower() in IMAGE_SUFFIXES,
        **settings,
    )
    parts = [compact_page_render(p) if p.get("page") else p for p in parts]
    return PartsResult(
        filename=result.document.filename,
        confidence=score,
        page_confidence=pages,
        processing_time=task_result.processing_time,
        parts=parts,
    )
