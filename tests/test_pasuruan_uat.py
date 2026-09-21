from decimal import Decimal

from app.services.vouching import parse_document_fields


def test_pasuruan_santoso_scanwise_extracts_billing_fields():
    text = """Nomor SPJ 2501787882
Nomor Faktur8501735930
Tanggal Faktur 24 Agustus 2026
Grand Total 2:350 000"""
    result = parse_document_fields(text)
    assert result["billing_document"] == "8501735930"
    assert result["no_spj"] == "2501787882"
    assert result["doc_date"].isoformat() == "2026-08-24"
    assert result["nominal"] == Decimal("2350000.00")
    assert result["partial_payment"] is None


def test_pasuruan_gemilang_scanwise_extracts_billing_fields():
    text = """Nomor SPJ 2501744403
Nomor Faktur 8501692627
Tanggal Faktur15 Juli 2026
Grand Totai 2.637280"""
    # OCR label corruption (Totai) remains reviewable evidence; field labels are not guessed.
    result = parse_document_fields(text)
    assert result["billing_document"] == "8501692627"
    assert result["no_spj"] == "2501744403"
    assert result["doc_date"].isoformat() == "2026-07-15"
