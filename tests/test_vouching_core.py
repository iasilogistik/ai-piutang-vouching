from datetime import date
from decimal import Decimal

from app.services.vouching import (
    _billing_document_from_filename,
    _normalize_spj_number,
    _normalize_ocr_amount_scale,
    _spj_numbers_match,
    parse_document_fields,
    _extract_partial_payments,
    _norm_key,
    _parse_amount,
    _parse_date,
)


def test_normalization_is_conservative():
    assert _norm_key("  bill-001 / A ") == "BILL001A"
    assert _parse_amount("Rp 1.500.000") == Decimal("1500000.00")
    assert _parse_date("01/09/2026") == date(2026, 9, 1)


def test_document_field_parser_keeps_raw_and_normalized_values():
    result = parse_document_fields("Billing Document: 900001\nNo SPJ: SPJ-77\nDoc. Date: 01/09/2026\nNominal: Rp 1.500.000")
    assert result["billing_document_raw"] == "900001"
    assert result["billing_document"] == "900001"
    assert result["no_spj_raw"] == "SPJ-77"
    assert result["no_spj"] == "SPJ77"
    assert result["doc_date"] == date(2026, 9, 1)
    assert result["nominal"] == Decimal("1500000.00")


def test_billing_document_filename_fallback_is_conservative():
    assert _billing_document_from_filename("Wonokoyo 8501681154.pdf") == "8501681154"
    assert _billing_document_from_filename("TB Joyo Arjuno prigen 8540088421.pdf") == "8540088421"
    assert _billing_document_from_filename("gemilang 86.pdf") is None
    assert _billing_document_from_filename("scan 8501681154 8501681202.pdf") is None
    assert _billing_document_from_filename("reference 123456789.pdf") is None



def test_partial_payment_parser_supports_common_scan_labels():
    amount, raw = _extract_partial_payments(
        "Payment Received: Rp 1.000.000\nDP: Rp 500.000"
    )

    assert amount == Decimal("1500000.00")
    assert "Payment Received" in raw
    assert "DP" in raw



def test_official_spj_reference_preserves_raw_and_matches_final_number():
    fields = parse_document_fields(
        "PT SEMEN INDONESIA DISTRIBUTOR\n"
        "SURAT PERINTAH JALAN\n"
        "SPJ/S41C/202608/2501787882\n"
        "Tanggal Pengiriman: 24-09-2026"
    )

    assert fields["no_spj_raw"] == "SPJ/S41C/202608/2501787882"
    assert fields["no_spj"] == "2501787882"
    assert _normalize_spj_number("SPJ/S41C/202608/2501787882") == "2501787882"


def test_partial_payment_parser_supports_paid_and_previous_payment_labels():
    amount, raw = _extract_partial_payments(
        "Amount Paid: Rp 1.000.000\nPembayaran Sebelumnya: Rp 500.000"
    )

    assert amount == Decimal("1500000.00")
    assert "Amount Paid" in raw
    assert "Pembayaran Sebelumnya" in raw



def test_spj_comparison_uses_final_transaction_number():
    assert _spj_numbers_match("2501787882", "SPJ/S41C/202608/2501787882") is True
    assert _spj_numbers_match("SPJ/S41C/202608/2501787882", "2501787882") is True
    assert _spj_numbers_match("2501787882", "2501787883") is False



def test_ocr_amount_scale_repairs_decimal_magnitude_loss():
    assert _normalize_ocr_amount_scale(
        Decimal("2.35"),
        Decimal("2350000.00"),
    ) == Decimal("2350000.00")
    assert _normalize_ocr_amount_scale(
        Decimal("5644800.00"),
        Decimal("1144600.00"),
        Decimal("4500200.00"),
    ) == Decimal("5644800.00")



def test_billing_date_parser_prioritizes_invoice_date_over_other_dates():
    fields = parse_document_fields(
        "Tanggal Pengiriman: 24-09-2026\n"
        "Billing Document: 8501735930\n"
        "Invoice Date: 25/09/2026\n"
        "Grand Total: 2.350.000"
    )

    assert fields["doc_date"] == date(2026, 9, 25)



def test_billing_date_parser_never_uses_due_date_or_jatuh_tempo():
    fields = parse_document_fields(
        "Billing Document: 8501735930\n"
        "Tanggal Faktur: 24/08/2026\n"
        "Jatuh Tempo: 23/09/2026\n"
        "Grand Total: 2.350.000"
    )
    assert fields["doc_date"] == date(2026, 8, 24)

    due_only = parse_document_fields(
        "Billing Document: 8501735930\n"
        "Due Date: 23/09/2026\n"
        "Grand Total: 2.350.000"
    )
    assert due_only["doc_date"] is None
