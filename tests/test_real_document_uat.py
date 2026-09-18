from decimal import Decimal

import pandas as pd

from app.services.sap_import import _import_sap_ledger
from app.services.vouching import _parse_amount, parse_document_fields


def test_real_sap_export_shape_aggregates_ledger_rows() -> None:
    frame = pd.DataFrame(
        [
            {
                "Billing Document": 8501681202,
                "Document Date": "2026-07-03",
                "Company Code Currency Value": 8815890,
                "Customer Account: Name 1": "BERKAH AL AQSO, TB",
            },
            {
                "Billing Document": 8501681202,
                "Document Date": "2026-09-10",
                "Company Code Currency Value": -3400008,
                "Customer Account: Name 1": "BERKAH AL AQSO, TB",
            },
            {
                "Billing Document": 8501709449,
                "Document Date": "2026-07-30",
                "Company Code Currency Value": 912500,
                "Customer Account: Name 1": "ICHA JAYA KENCANO SAKTI",
            },
        ]
    )

    rows = _import_sap_ledger(frame)

    by_billing = {row["billing_document"]: row for row in rows}
    assert by_billing["8501681202"]["nominal"] == Decimal("5415882.00")
    assert by_billing["8501709449"]["nominal"] == Decimal("912500.00")
    assert by_billing["8501681202"]["doc_date"].isoformat() == "2026-09-10"


def test_scanned_billing_labels_are_extracted() -> None:
    text = """
    INFORMASI PEMBAYARAN
    Nomor SPJ 2501731412
    Nomor Faktur 8501681202
    Tanggal Faktur 03 Juli 2026
    Sub Total 7.942.224
    PPN 873.666
    Grand Total 8.815.890
    """
    fields = parse_document_fields(text)

    assert fields["billing_document"] == "8501681202"
    assert fields["no_spj"] == "2501731412"
    assert fields["doc_date"].isoformat() == "2026-07-03"
    assert fields["nominal"] == Decimal("8815890.00")


def test_scanned_spj_header_normalizes_to_numeric_spj() -> None:
    text = """
    SURAT PERINTAH JALAN
    SPJ/S41C/202608/2540226757
    Tanggal Pengiriman : 01-08-2026
    """
    fields = parse_document_fields(text)

    assert fields["no_spj"] == "2540226757"


def test_grand_total_is_not_replaced_by_sub_total() -> None:
    text = """
    Sub Total 513.513
    PPN 56.437
    Grand Total 570.000
    """
    assert parse_document_fields(text)["nominal"] == Decimal("570000.00")
