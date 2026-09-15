from datetime import date
from decimal import Decimal

from app.services.vouching import _norm_key, _parse_amount, _parse_date, parse_document_fields


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
