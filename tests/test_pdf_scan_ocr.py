from datetime import date
import sys
import types

from app.services.vouching import _parse_date, extract_text


def test_parse_indonesian_month_date():
    assert _parse_date("24 Agustus 2026") == date(2026, 8, 24)
    assert _parse_date("15 Juli 2026") == date(2026, 7, 15)


def test_pdf_without_text_layer_falls_back_to_tesseract(monkeypatch, tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"not-a-real-pdf")

    class FakePage:
        def get_pixmap(self, matrix=None, alpha=False):
            return types.SimpleNamespace(tobytes=lambda fmt: b"image-bytes")

    class FakeDoc:
        def __iter__(self):
            return iter([FakePage()])

        def close(self):
            pass

    fake_fitz = types.SimpleNamespace(
        Matrix=lambda x, y: (x, y),
        open=lambda path: FakeDoc(),
    )
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)
    monkeypatch.setattr("pytesseract.image_to_string", lambda image, **kwargs: "Billing No: 8501735930")

    text, engine = extract_text(str(pdf))

    assert text == "Billing No: 8501735930"
    assert engine == "TESSERACT_PDF"
