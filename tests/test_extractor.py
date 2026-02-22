"""Tests for PDF extractor → ExtractionObject."""

from pathlib import Path

import pytest

from backend.pipeline.extractor import extract_from_pdf


def test_extract_from_pdf_returns_extraction_object():
    """Minimal PDF bytes still produce a valid ExtractionObject."""
    # Minimal valid PDF (single page, no real content)
    minimal_pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
xref
0 4
trailer<</Size 4/Root 1 0 R>>
startxref
0
%%EOF"""
    result = extract_from_pdf(minimal_pdf, state_id="state_test_1")
    assert result.state_id == "state_test_1"
    assert isinstance(result.extracted_text, str)
    assert isinstance(result.vendor_name, str)
    assert isinstance(result.items, list)
    assert result.tax >= 0
    assert result.shipping >= 0
    assert result.total_invoice_price >= 0


def test_extract_from_pdf_with_real_invoice():
    """Extract from a real invoice PDF in data/ if present."""
    data_dir = Path(__file__).resolve().parent.parent / "data"
    pdf_path = data_dir / "Invoice_Type_1_Clean_Corporate (1).pdf"
    if not pdf_path.is_file():
        pytest.skip("Sample PDF not found")
    pdf_bytes = pdf_path.read_bytes()
    result = extract_from_pdf(pdf_bytes, state_id="state_real_1")
    assert result.state_id == "state_real_1"
    assert len(result.extracted_text) > 0
    assert result.vendor_name
    assert isinstance(result.items, list)
    for item in result.items:
        assert item.item_id
        assert item.item_name is not None
        assert item.number_of_items >= 0
        assert item.total_price_of_item >= 0
        assert item.unit_price >= 0
