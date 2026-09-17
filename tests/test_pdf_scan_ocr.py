from datetime import date

import app.services.vouching as vouching


def test_parse_indonesian_month_date():
    assert vouching._parse_date("24 Agustus 2026") == date(2026, 8, 24)
    assert vouching._parse_date("15 Juli 2026") == date(2026, 7, 15)


def test_pdf_without_text_layer_falls_back_to_tesseract(monkeypatch, tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"not-a-real-pdf")
    monkeypatch.setattr(vouching, "_ocr_pdf_scan", lambda path: ("Billing No: 8501735930", "TESSERACT_PDF"))
    monkeypatch.setattr(vouching, "PdfReader", None, raising=False)
    text, engine = vouching.extract_text(str(pdf))
    assert text == "Billing No: 8501735930"
    assert engine == "TESSERACT_PDF"


def test_parse_partial_payments_and_sum():
    text = "Billing No: 8501735930\nGrand Total: Rp10.000.000\nPembayaran Partial: Rp2.000.000\nPartial Payment: Rp1.000.000"
    fields = vouching.parse_document_fields(text)
    assert fields["partial_payment"] == 3000000
    assert fields["partial_payment_raw"] == "Rp2.000.000; Partial Payment: Rp1.000.000"


def test_net_amount_uses_billing_and_spj_partial_payment():
    assert vouching._net_document_amount(10000000, 2000000, 1000000) == 7000000
