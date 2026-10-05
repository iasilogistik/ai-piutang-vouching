from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    ControlEvidenceDetection,
    Document,
    DocumentControlEvidence,
    PhysicalBilling,
    SPJ,
)
from app.services.control_evidence_store import analyze_and_persist_control_evidence
from app.services.vision_evidence import partial_payment_summary
import app.services.vouching as vouching


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _vision_payload():
    return {
        "engine": "AI_VISION",
        "model": "test-model",
        "billing_document": "8540088421",
        "invoice_date": date(2025, 9, 6),
        "grand_total": Decimal("5644800.00"),
        "spj_number": "2540165212",
        "delivery_order_number": "255020729",
        "receiver_name": "Joyo Arjuno",
        "partial_payments": [
            {
                "amount": Decimal("4500200.00"),
                "date": date(2025, 9, 8),
                "reference": "Payment received",
            }
        ],
        "signatures": {
            "receiver": {"status": "PRESENT", "confidence": 0.96, "page_number": 1},
            "driver": {"status": "PRESENT", "confidence": 0.93, "page_number": 1},
            "security": {"status": "PRESENT", "confidence": 0.91, "page_number": 1},
            "bm": {"status": "PRESENT", "confidence": 0.88, "page_number": 2},
            "checker": {"status": "PRESENT", "confidence": 0.94, "page_number": 1},
        },
        "stamp": {
            "status": "PRESENT",
            "text": "TB JOYO ARJUNO PRIGEN",
            "confidence": 0.95,
            "page_number": 1,
        },
        "notes": [],
    }


def test_partial_payment_summary_sums_structured_vision_rows():
    total, raw = partial_payment_summary(_vision_payload())

    assert total == Decimal("4500200.00")
    assert "4500200.00" in raw
    assert "Payment received" in raw


def test_spj_vision_enriches_paired_billing_without_double_counting(monkeypatch, tmp_path):
    monkeypatch.setattr(vouching, "extract_text", lambda path: ("", "REVIEW_REQUIRED"))
    monkeypatch.setattr(vouching, "vision_available", lambda: True)
    monkeypatch.setattr(
        vouching,
        "analyze_document_vision",
        lambda *args, **kwargs: _vision_payload(),
    )

    fake_pdf = tmp_path / "TB Joyo Arjuno Prigen 8540088421.pdf"
    fake_pdf.write_bytes(b"%PDF-test")

    with Session(_engine()) as db:
        billing_doc = Document(
            file_name=fake_pdf.name,
            file_type="PDF",
            document_type="BILLING",
            file_hash="same-hash",
            storage_path=str(fake_pdf),
            branch="KEDIRI",
        )
        spj_doc = Document(
            file_name=fake_pdf.name,
            file_type="PDF",
            document_type="SPJ",
            file_hash="same-hash",
            storage_path=str(fake_pdf),
            branch="KEDIRI",
        )
        db.add_all([billing_doc, spj_doc])
        db.flush()
        billing = PhysicalBilling(document_id=billing_doc.id)
        spj = SPJ(document_id=spj_doc.id)
        db.add_all([billing, spj])
        db.commit()

        result = vouching.ocr_document(
            db,
            spj_doc.id,
            expected_customer="TB JOYO ARJUNO PRIGEN",
            expected_billing_document="8540088421",
            expected_nominal=Decimal("1144600.00"),
        )
        db.refresh(billing)
        db.refresh(spj)

        assert result["engine"] == "AI_VISION"
        assert billing.billing_document == "8540088421"
        assert billing.no_spj == "2540165212"
        assert billing.doc_date == date(2025, 9, 6)
        assert billing.nominal == Decimal("5644800.00")
        assert billing.partial_payment == Decimal("4500200.00")
        assert spj.no_spj == "2540165212"
        assert spj.partial_payment is None


def test_visual_control_evidence_reads_signatures_stamp_and_receiver(monkeypatch, tmp_path):
    import app.services.vouching as vouching_module

    monkeypatch.setattr(vouching_module, "extract_text", lambda path: ("", "REVIEW_REQUIRED"))

    fake_pdf = tmp_path / "sample.pdf"
    fake_pdf.write_bytes(b"%PDF-test")

    with Session(_engine()) as db:
        doc = Document(
            file_name=fake_pdf.name,
            file_type="PDF",
            document_type="SPJ",
            file_hash="vision-hash",
            storage_path=str(fake_pdf),
            branch="KEDIRI",
        )
        db.add(doc)
        db.flush()
        db.add(SPJ(document_id=doc.id, no_spj="2540165212"))
        db.commit()

        payload = analyze_and_persist_control_evidence(
            db,
            doc.id,
            expected_customer="TB JOYO ARJUNO PRIGEN",
            vision_result=_vision_payload(),
        )
        db.commit()

        row = db.scalar(
            select(DocumentControlEvidence).where(DocumentControlEvidence.document_id == doc.id)
        )
        receiver_detection = db.scalar(
            select(ControlEvidenceDetection).where(
                ControlEvidenceDetection.document_id == doc.id,
                ControlEvidenceDetection.detection_type == "receiver_signature",
            )
        )

        assert payload["vision_used"] is True
        assert payload["receiver_name"] is None
        assert row.receiver_signature_status == "PRESENT"
        assert row.driver_signature_status == "PRESENT"
        assert row.security_signature_status == "PRESENT"
        assert row.bm_signature_status == "PRESENT"
        assert row.checker_signature_status == "PRESENT"
        assert row.receiver_stamp_status == "PRESENT"
        assert row.stamp_customer_match_status == "MATCH"
        assert row.review_required is False
        assert receiver_detection is not None
        assert receiver_detection.reference_json == {"source": "AI_VISION"}



def test_visual_control_evidence_accepts_not_applicable_template_role(monkeypatch, tmp_path):
    import app.services.vouching as vouching_module

    monkeypatch.setattr(vouching_module, "extract_text", lambda path: ("", "REVIEW_REQUIRED"))
    vision = _vision_payload()
    vision["receiver_name"] = None
    vision["signatures"]["bm"] = {
        "status": "NOT_APPLICABLE",
        "confidence": 0.9,
        "page_number": None,
    }

    fake_pdf = tmp_path / "template-without-bm.pdf"
    fake_pdf.write_bytes(b"%PDF-test")

    with Session(_engine()) as db:
        doc = Document(
            file_name=fake_pdf.name,
            file_type="PDF",
            document_type="SPJ",
            file_hash="vision-na-hash",
            storage_path=str(fake_pdf),
            branch="KEDIRI",
        )
        db.add(doc)
        db.flush()
        db.add(SPJ(document_id=doc.id, no_spj="2540165212"))
        db.commit()

        payload = analyze_and_persist_control_evidence(
            db,
            doc.id,
            expected_customer="TB JOYO ARJUNO PRIGEN",
            vision_result=vision,
        )
        db.commit()

        row = db.scalar(
            select(DocumentControlEvidence).where(DocumentControlEvidence.document_id == doc.id)
        )
        assert row.bm_signature_status == "NOT_APPLICABLE"
        assert row.review_required is False
        assert payload["receiver_name"] is None



def test_ocr_forwards_expected_doc_date_to_visual_engine(monkeypatch, tmp_path):
    monkeypatch.setattr(vouching, "extract_text", lambda path: ("", "REVIEW_REQUIRED"))
    monkeypatch.setattr(vouching, "vision_available", lambda: True)
    captured = {}

    def fake_vision(*args, **kwargs):
        captured.update(kwargs)
        payload = _vision_payload()
        payload["invoice_date"] = date(2026, 8, 24)
        return payload

    monkeypatch.setattr(vouching, "analyze_document_vision", fake_vision)

    fake_pdf = tmp_path / "SANTOSO 8501735930.pdf"
    fake_pdf.write_bytes(b"%PDF-test")

    with Session(_engine()) as db:
        doc = Document(
            file_name=fake_pdf.name,
            file_type="PDF",
            document_type="BILLING",
            file_hash="invoice-date-hash",
            storage_path=str(fake_pdf),
            branch="KEDIRI",
        )
        db.add(doc)
        db.flush()
        billing = PhysicalBilling(document_id=doc.id)
        db.add(billing)
        db.commit()

        vouching.ocr_document(
            db,
            doc.id,
            expected_customer="SANTOSO, TOKO",
            expected_billing_document="8501735930",
            expected_nominal=Decimal("2350000.00"),
            expected_doc_date=date(2026, 8, 24),
            force_vision=True,
        )
        db.refresh(billing)

        assert captured["expected_doc_date"] == date(2026, 8, 24)
        assert billing.doc_date == date(2026, 8, 24)



def test_unclear_visual_stamp_never_auto_passes(monkeypatch, tmp_path):
    import app.services.vouching as vouching_module

    monkeypatch.setattr(vouching_module, "extract_text", lambda path: ("", "REVIEW_REQUIRED"))
    vision = _vision_payload()
    vision["stamp"] = {
        "status": "UNCLEAR",
        "text": None,
        "confidence": 0.35,
        "page_number": 1,
    }

    fake_pdf = tmp_path / "signature-without-clear-stamp.pdf"
    fake_pdf.write_bytes(b"%PDF-test")

    with Session(_engine()) as db:
        doc = Document(
            file_name=fake_pdf.name,
            file_type="PDF",
            document_type="SPJ",
            file_hash="unclear-stamp-hash",
            storage_path=str(fake_pdf),
            branch="KEDIRI",
        )
        db.add(doc)
        db.flush()
        db.add(SPJ(document_id=doc.id, no_spj="2501787882"))
        db.commit()

        payload = analyze_and_persist_control_evidence(
            db,
            doc.id,
            expected_customer="SANTOSO, TOKO",
            vision_result=vision,
        )
        db.commit()

        row = db.scalar(
            select(DocumentControlEvidence).where(DocumentControlEvidence.document_id == doc.id)
        )
        assert row.receiver_stamp_status == "UNKNOWN"
        assert row.review_required is True
        assert "stempel" in (row.review_reasons or "").lower()
        assert payload["review_required"] is True



def test_v14_refresh_persists_derived_partial_and_only_invoice_date(monkeypatch, tmp_path):
    monkeypatch.setattr(vouching, "extract_text", lambda path: ("", "REVIEW_REQUIRED"))
    monkeypatch.setattr(vouching, "vision_available", lambda: True)

    vision = _vision_payload()
    vision["engine"] = "LOCAL_TESSERACT_VISUAL_V14"
    vision["invoice_date"] = date(2026, 9, 10)
    vision["partial_payments"] = [
        {
            "amount": Decimal("999950.00"),
            "date": None,
            "reference": "DERIVED_BILLING_GROSS_MINUS_SAP_OUTSTANDING | Gross 2637230 | SAP Outstanding 1637280",
        }
    ]
    vision["grand_total"] = Decimal("2637230.00")

    monkeypatch.setattr(vouching, "analyze_document_vision", lambda *args, **kwargs: vision)

    fake_pdf = tmp_path / "gemilang 86.pdf"
    fake_pdf.write_bytes(b"%PDF-test")

    with Session(_engine()) as db:
        billing_doc = Document(
            file_name=fake_pdf.name,
            file_type="PDF",
            document_type="BILLING",
            file_hash="same-gemilang-hash",
            storage_path=str(fake_pdf),
            branch="KEDIRI",
        )
        spj_doc = Document(
            file_name=fake_pdf.name,
            file_type="PDF",
            document_type="SPJ",
            file_hash="same-gemilang-hash",
            storage_path=str(fake_pdf),
            branch="KEDIRI",
        )
        db.add_all([billing_doc, spj_doc])
        db.flush()
        billing = PhysicalBilling(
            document_id=billing_doc.id,
            billing_document="8501692627",
            doc_date=None,
            nominal=Decimal("2637230.00"),
        )
        spj = SPJ(document_id=spj_doc.id)
        db.add_all([billing, spj])
        db.commit()

        vouching.ocr_document(
            db,
            spj_doc.id,
            expected_customer="GEMILANG 86, TB",
            expected_billing_document="8501692627",
            expected_nominal=Decimal("1637280.00"),
            expected_doc_date=date(2026, 9, 10),
            force_vision=True,
        )
        db.refresh(billing)

        assert billing.doc_date == date(2026, 9, 10)
        assert billing.nominal == Decimal("2637230.00")
        assert billing.partial_payment == Decimal("999950.00")
        assert "DERIVED_BILLING_GROSS_MINUS_SAP_OUTSTANDING" in (billing.partial_payment_raw or "")
