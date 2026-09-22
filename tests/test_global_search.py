from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.config import settings
from app.database import Base
from app.main import app
from app.models import (
    AuditEngagement,
    AuditFinding,
    AuditReport,
    AuditSample,
    AuditPopulation,
    AuditWorkingPaper,
    CorrectiveActionPlan,
    CorrectiveActionProgressUpdate,
    Document,
    ImportBatch,
    ManagementResponse,
    SAPBilling,
)
from app.services.global_search import build_search_export, search_audit_records
from app.services.navigation import navigation_html


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _seed(db):
    pas = AuditEngagement(
        code="AUD-PAS-SEARCH",
        title="Audit Piutang Pasuruan",
        branch="PASURUAN",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        scope="Piutang dan penagihan",
        status="IN_PROGRESS",
        created_by="admin",
    )
    sda = AuditEngagement(
        code="AUD-SDA-SEARCH",
        title="Audit Piutang Sidoarjo",
        branch="SIDOARJO",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        scope="Cabang lain",
        status="IN_PROGRESS",
        created_by="admin",
    )
    db.add_all([pas, sda])
    db.flush()

    population = AuditPopulation(
        engagement_id=pas.id,
        branch="PASURUAN",
        name="Piutang September",
        population_type="RECEIVABLE",
        source_type="SAP",
        total_records=2,
        created_by="auditor-1",
    )
    db.add(population)
    db.flush()
    sample = AuditSample(
        engagement_id=pas.id,
        population_id=population.id,
        branch="PASURUAN",
        source_record_ref="INV-PAS-001",
        selection_method="MANUAL",
        selection_reason="High value",
        status="SELECTED",
        selected_by="auditor-1",
    )
    db.add(sample)

    wp = AuditWorkingPaper(
        engagement_id=pas.id,
        branch="PASURUAN",
        reference="WP-SEARCH-01",
        title="Vouching kontra bon",
        audit_objective="Memastikan dokumen penagihan",
        procedure_performed="Vouch dokumen",
        result_observation="Kontra bon tidak valid",
        conclusion="Perlu finding",
        preparer_id="auditor-1",
        status="REVIEWED",
    )
    db.add(wp)

    finding = AuditFinding(
        engagement_id=pas.id,
        branch="PASURUAN",
        reference="F-SEARCH-01",
        title="Penagihan tanpa dokumen valid",
        condition="Kontra bon tidak dapat diverifikasi",
        criteria="Dokumen wajib valid",
        cause="Kontrol lemah",
        effect_risk="Risiko penyalahgunaan penerimaan",
        recommendation="Perkuat validasi dokumen",
        severity="HIGH",
        status="ISSUED",
        preparer_id="auditor-1",
        reviewer_id="reviewer-1",
    )
    other_finding = AuditFinding(
        engagement_id=sda.id,
        branch="SIDOARJO",
        reference="F-SDA-SECRET",
        title="Sidoarjo restricted record",
        condition="Condition",
        criteria="Criteria",
        cause="Cause",
        effect_risk="Risk",
        recommendation="Recommendation",
        severity="LOW",
        status="ISSUED",
        preparer_id="auditor-2",
    )
    db.add_all([finding, other_finding])
    db.flush()

    response = ManagementResponse(
        finding_id=finding.id,
        branch="PASURUAN",
        response_text="Manajemen setuju memperbaiki kontrol.",
        position="AGREE",
        status="ACCEPTED",
        submitted_by="manager-1",
    )
    db.add(response)
    db.flush()
    action = CorrectiveActionPlan(
        finding_id=finding.id,
        response_id=response.id,
        branch="PASURUAN",
        action_description="Rekonsiliasi TTP harian",
        external_pic_name="Branch Manager",
        target_date=date(2026, 10, 1),
        status="IN_PROGRESS",
        created_by="auditor-1",
    )
    db.add(action)
    db.flush()
    db.add(
        CorrectiveActionProgressUpdate(
            action_plan_id=action.id,
            branch="PASURUAN",
            update_text="Rekonsiliasi sudah diterapkan 50 persen.",
            progress_percent=50,
            submitted_by="auditor-1",
        )
    )

    doc = Document(
        file_name="kontra-bon-master-bangunan.pdf",
        file_type="PDF",
        document_type="SPJ",
        file_hash="a" * 64,
        storage_path="/tmp/evidence-search.pdf",
        uploaded_by="auditor-1",
        branch="PASURUAN",
        engagement_id=pas.id,
        evidence_classification="COLLECTION",
        evidence_source="CUSTOMER",
        description="Kontra bon pelanggan Master Bangunan",
        file_size_bytes=100,
        mime_type="application/pdf",
    )
    db.add(doc)

    db.add(
        AuditReport(
            engagement_id=pas.id,
            branch="PASURUAN",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            status="APPROVED",
            finding_summary="Penagihan memerlukan perbaikan.",
            conclusion="Kontrol perlu diperkuat.",
            created_by="auditor-1",
            approved_by="reviewer-1",
        )
    )

    batch = ImportBatch(
        file_name="sap-search.xlsx",
        branch="PASURUAN",
        uploaded_by="auditor-1",
        total_records=1,
        status="VALIDATED",
    )
    db.add(batch)
    db.flush()
    db.add(
        SAPBilling(
            import_batch_id=batch.id,
            customer="CUST-001",
            customer_account_name="Master Bangunan",
            billing_document="9000123456",
            doc_date=date(2026, 9, 15),
            nominal=1000000,
        )
    )
    db.flush()
    return pas, sda


def test_search_partial_text_customer_and_reference():
    with Session(_engine()) as db:
        _seed(db)
        customer = search_audit_records(
            db, query_text="Master Bangunan", branch="PASURUAN", page_size=100
        )
        types = {x["resource_type"] for x in customer["results"]}
        assert "EVIDENCE" in types
        assert "SAP_BILLING" in types

        sample = search_audit_records(
            db, query_text="INV-PAS", branch="PASURUAN", page_size=100
        )
        assert [(x["resource_type"], x["reference"]) for x in sample["results"]] == [
            ("SAMPLE", "INV-PAS-001")
        ]


def test_search_branch_isolation_and_resource_filters():
    with Session(_engine()) as db:
        pas, _ = _seed(db)
        payload = search_audit_records(
            db,
            branch="PASURUAN",
            resource_type="FINDING",
            status="ISSUED",
            owner="auditor-1",
            engagement_id=pas.id,
            page_size=100,
        )
        assert payload["total"] == 1
        assert payload["results"][0]["reference"] == "F-SEARCH-01"
        assert all(x["branch"] == "PASURUAN" for x in payload["results"])
        assert all("SDA" not in x["reference"] for x in payload["results"])


def test_search_pagination_is_deterministic():
    with Session(_engine()) as db:
        pas, _ = _seed(db)
        for idx in range(2, 6):
            db.add(
                AuditFinding(
                    engagement_id=pas.id,
                    branch="PASURUAN",
                    reference=f"F-PAGE-{idx}",
                    title=f"Pagination finding {idx}",
                    condition="Condition",
                    criteria="Criteria",
                    cause="Cause",
                    effect_risk="Risk",
                    recommendation="Recommendation",
                    severity="MEDIUM",
                    status="DRAFT",
                    preparer_id="auditor-1",
                )
            )
        db.flush()

        first = search_audit_records(
            db, branch="PASURUAN", resource_type="FINDING", page=1, page_size=2
        )
        second = search_audit_records(
            db, branch="PASURUAN", resource_type="FINDING", page=2, page_size=2
        )
        assert first["total"] == 5
        assert len(first["results"]) == 2
        assert len(second["results"]) == 2
        assert {x["id"] for x in first["results"]}.isdisjoint({x["id"] for x in second["results"]})


def test_export_matches_authorized_filtered_results():
    with Session(_engine()) as db:
        _seed(db)
        payload = search_audit_records(
            db,
            query_text="penagihan",
            branch="PASURUAN",
            page_size=100,
        )
        rows = payload["results"]
        content, media_type, filename = build_search_export(rows, "csv")
        text = content.decode("utf-8-sig")
        assert filename == "audit_search.csv"
        assert media_type.startswith("text/csv")
        assert len(text.strip().splitlines()) == len(rows) + 1
        assert "SIDOARJO" not in text
        assert "F-SEARCH-01" in text


def test_navigation_contains_authenticated_global_search_input():
    html = navigation_html(
        CurrentUser(user_id="auditor-1", role="AUDITOR", branch="PASURUAN"),
        unread_count=3,
    )
    assert 'action="/ui/search"' in html
    assert 'name="q"' in html
    assert "Notifications (3)" in html


def test_search_routes_are_served_and_protected(monkeypatch):
    client = TestClient(app)
    ui = client.get("/ui/search")
    assert ui.status_code == 200
    assert "Global Audit Search" in ui.text

    monkeypatch.setattr(settings, "auth_required", True)
    assert client.get("/search").status_code == 401
    assert client.get("/search/export").status_code == 401
