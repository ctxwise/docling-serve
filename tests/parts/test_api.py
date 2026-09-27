"""/parts endpoint helpers: docling options, page render compaction, and result building."""

import base64
import io

import pytest
from fastapi import HTTPException
from PIL import Image

from docling.datamodel.base_models import (
    ConversionStatus,
    DoclingComponentType,
    ErrorItem,
    OutputFormat,
)
from docling.datamodel.service.options import ConvertDocumentsOptions
from docling.datamodel.service.responses import (
    ConfidenceScores,
    DoclingTaskResult,
    ExportDocumentResponse,
    ExportResult,
    ZipArchiveResult,
)
from docling_core.types.doc import (
    BoundingBox,
    DocItemLabel,
    DoclingDocument,
    ImageRef,
    ImageRefMode,
    ProvenanceItem,
    Size,
)
from docling_core.types.doc.document import DocumentOrigin

from docling_serve.parts.api import (
    PAGE_RENDER_MAX_SIDE,
    PartsOptions,
    compact_page_render,
    convert_options_for,
    to_parts_result,
)
from docling_serve.parts.confidence import PageConfidenceScores

# convert_options_for


def test_convert_options_force_what_parts_need():
    options = convert_options_for(
        ConvertDocumentsOptions(to_formats=[OutputFormat.MARKDOWN]),
        PartsOptions(max_pages=7),
    )
    assert options.to_formats == [OutputFormat.JSON]
    assert options.image_export_mode == ImageRefMode.EMBEDDED
    assert options.page_range == (1, 7)


def test_convert_options_pages_mode_skips_picture_crops():
    options = convert_options_for(
        ConvertDocumentsOptions(), PartsOptions(mode="pages", min_confidence=0)
    )
    assert options.include_images is False
    assert options.do_picture_classification is False
    assert options.include_page_images is True


def test_convert_options_docling_mode_keeps_picture_crops():
    options = convert_options_for(ConvertDocumentsOptions(), PartsOptions())
    assert options.include_images is True
    assert options.do_picture_classification is True
    assert options.include_page_images is True  # min_confidence 0.8 needs renders


def test_convert_options_docling_mode_without_confidence_skips_page_renders():
    options = convert_options_for(
        ConvertDocumentsOptions(), PartsOptions(min_confidence=0)
    )
    assert options.include_page_images is False


def test_convert_options_keep_other_user_options():
    options = convert_options_for(
        ConvertDocumentsOptions(ocr_lang=["de"], do_ocr=False), PartsOptions()
    )
    assert options.ocr_lang == ["de"]
    assert options.do_ocr is False


def test_convert_options_do_not_mutate_the_request():
    request = ConvertDocumentsOptions(to_formats=[OutputFormat.MARKDOWN])
    convert_options_for(request, PartsOptions(mode="pages"))
    assert request.to_formats == [OutputFormat.MARKDOWN]
    assert request.page_range != (1, 100)


# compact_page_render


def png_b64(width: int, height: int) -> str:
    buffer = io.BytesIO()
    Image.effect_noise((width, height), 64).convert("RGB").save(buffer, "PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def decode(part: dict) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(part["data"])))


def test_compact_page_render_shrinks_a_large_png_to_jpeg():
    data = png_b64(3000, 2000)
    part = compact_page_render(
        {"type": "image", "media_type": "image/png", "data": data, "page": 3}
    )
    image = decode(part)
    assert part["media_type"] == "image/jpeg"
    assert image.format == "JPEG"
    assert max(image.size) == PAGE_RENDER_MAX_SIDE
    assert len(part["data"]) < len(data) / 4


def test_compact_page_render_does_not_upscale():
    part = compact_page_render(
        {"type": "image", "media_type": "image/png", "data": png_b64(400, 300)}
    )
    assert decode(part).size == (400, 300)


def test_compact_page_render_keeps_other_keys():
    part = compact_page_render(
        {"type": "image", "media_type": "image/png", "data": png_b64(10, 10), "page": 2}
    )
    assert part["type"] == "image"
    assert part["page"] == 2


# to_parts_result


def task_result(result, processing_time: float = 1.5) -> DoclingTaskResult:
    return DoclingTaskResult(
        result=result,
        processing_time=processing_time,
        num_converted=1,
        num_succeeded=1,
        num_failed=0,
    )


def pdf_document() -> DoclingDocument:
    """Two rendered pages: page 1 blank-ish, page 2 with text and a picture."""
    doc = DoclingDocument(
        name="report",
        origin=DocumentOrigin(
            mimetype="application/pdf", binary_hash=1, filename="report.pdf"
        ),
    )
    for n in (1, 2):
        render = Image.effect_noise((2000, 2600), 64).convert("RGB")
        doc.add_page(
            page_no=n,
            size=Size(width=1000, height=1300),
            image=ImageRef.from_pil(render, dpi=144),
        )
    prov = ProvenanceItem(
        page_no=2, bbox=BoundingBox(l=10, t=10, r=200, b=100), charspan=(0, 5)
    )
    doc.add_text(label=DocItemLabel.TEXT, text="Revenue grew.", prov=prov)
    crop = Image.new("RGB", (300, 200), "red")
    doc.add_picture(image=ImageRef.from_pil(crop, dpi=72), prov=prov)
    return doc


def export_result(doc: DoclingDocument | None, **fields) -> ExportResult:
    return ExportResult(
        document=ExportDocumentResponse(filename="report.pdf", json_content=doc),
        status=ConversionStatus.SUCCESS if doc else ConversionStatus.FAILURE,
        **fields,
    )


def test_to_parts_result_rejects_non_export_results():
    with pytest.raises(HTTPException) as error:
        to_parts_result(task_result(ZipArchiveResult(content=b"")), PartsOptions())
    assert error.value.status_code == 400


def test_to_parts_result_reports_conversion_errors():
    result = export_result(
        None,
        errors=[
            ErrorItem(
                component_type=DoclingComponentType.DOCUMENT_BACKEND,
                module_name="pdf",
                error_message="bad xref",
            ),
            ErrorItem(
                component_type=DoclingComponentType.DOCUMENT_BACKEND,
                module_name="pdf",
                error_message="no pages",
            ),
        ],
    )
    with pytest.raises(HTTPException) as error:
        to_parts_result(task_result(result), PartsOptions())
    assert error.value.status_code == 422
    assert "bad xref; no pages" in error.value.detail


def test_to_parts_result_builds_the_result():
    confidence = PageConfidenceScores(low_score=0.5, pages={1: 0.5, 2: 0.95})
    result = to_parts_result(
        task_result(export_result(pdf_document(), confidence=confidence), 2.5),
        PartsOptions(),
    )
    assert result.filename == "report.pdf"
    assert result.confidence == 0.5
    assert result.page_confidence == {1: 0.5, 2: 0.95}
    assert result.processing_time == 2.5


def test_to_parts_result_compacts_page_renders_only():
    confidence = PageConfidenceScores(low_score=0.5, pages={1: 0.5, 2: 0.95})
    result = to_parts_result(
        task_result(export_result(pdf_document(), confidence=confidence)),
        PartsOptions(),
    )
    images = [p for p in result.parts if p.type == "image"]
    page_render, crop = images
    assert page_render.page == 1  # the low-confidence page
    assert page_render.media_type == "image/jpeg"
    assert max(decode(page_render.model_dump()).size) == PAGE_RENDER_MAX_SIDE
    assert crop.page is None
    assert crop.media_type == "image/png"
    assert decode(crop.model_dump()).size == (300, 200)


def test_to_parts_result_falls_back_to_the_document_score():
    result = to_parts_result(
        task_result(
            export_result(pdf_document(), confidence=ConfidenceScores(low_score=0.9))
        ),
        PartsOptions(),
    )
    assert result.confidence == 0.9
    assert result.page_confidence == {}
