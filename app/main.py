from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.audit_service import list_audit_trail, record_audit
from app.database import SessionLocal, engine
from app.models import BillingReconciliation, Document, ImportBatch, PhysicalBilling, SPJ, VouchingResult
from app.services.reports import build_report
from app.services.sap_import import import_sap_upload
from app.services.vouching import ocr_document, overall_result, reconcile_batch, save_document, validate_sap_batch, vouch_spj

app = FastAPI(title="AI Piutang Vouching")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def handle_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/health")
def health() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "healthy"}


@app.post("/sap/import")
def sap_import(file: UploadFile = File(...), period: date | None = None,
               uploaded_by: str | None = None, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        batch = import_sap_upload(db, file, uploaded_by=uploaded_by, period=period)
        record_audit(db, entity_type="IMPORT_BATCH", entity_id=batch.id, action="SAP_IMPORT",
                     actor=uploaded_by, status_to=batch.status, metadata={"file_name": batch.file_name, "total_records": batch.total_records})
        db.commit()
    except ValueError as exc:
        db.rollback(); raise handle_error(exc) from exc
    return {"batch_id": batch.id, "file_name": batch.file_name, "period": batch.period.isoformat() if batch.period else None,
            "total_records": batch.total_records, "status": batch.status}


@app.get("/sap/validate/{batch_id}")
def sap_validate(batch_id: int, db: Session = Depends(get_db)):
    try: return validate_sap_batch(db, batch_id)
    except ValueError as exc: raise handle_error(exc) from exc


@app.post("/documents/{document_type}")
def upload_document(document_type: str, file: UploadFile = File(...), uploaded_by: str | None = None,
                    db: Session = Depends(get_db)):
    document_type = document_type.upper()
    if document_type not in {"BILLING", "SPJ"}:
        raise HTTPException(status_code=400, detail="document_type must be BILLING or SPJ")
    try:
        doc = save_document(db, file, document_type=document_type, uploaded_by=uploaded_by)
        record_audit(db, entity_type="DOCUMENT", entity_id=doc.id, action="UPLOAD", actor=uploaded_by,
                     status_to="UPLOADED", metadata={"document_type": document_type, "file_name": doc.file_name, "file_hash": doc.file_hash})
        db.commit()
    except ValueError as exc:
        db.rollback(); raise handle_error(exc) from exc
    return {"document_id": doc.id, "file_name": doc.file_name, "document_type": doc.document_type, "file_hash": doc.file_hash}


@app.post("/documents/{document_id}/ocr")
def run_ocr(document_id: int, db: Session = Depends(get_db)):
    try:
        result = ocr_document(db, document_id)
        record_audit(db, entity_type="DOCUMENT", entity_id=document_id, action="OCR",
                     status_to="OCR_PROCESSED", metadata={"engine": result.get("engine"), "confidence": result.get("confidence")})
        db.commit()
        return result
    except ValueError as exc: raise handle_error(exc) from exc


@app.post("/reconciliation/{batch_id}/run")
def run_reconciliation(batch_id: int, db: Session = Depends(get_db)):
    try:
        rows = reconcile_batch(db, batch_id)
        record_audit(db, entity_type="IMPORT_BATCH", entity_id=batch_id, action="RECONCILIATION_RUN",
                     status_to="COMPLETED", metadata={"total": len(rows)})
        db.commit()
    except ValueError as exc: raise handle_error(exc) from exc
    return {"batch_id": batch_id, "total": len(rows), "results": [{"id": r.id, "status": r.status,
        "exception_code": r.exception_code, "nominal_difference": str(r.nominal_difference)} for r in rows]}


@app.get("/reconciliation/{batch_id}")
def reconciliation_dashboard(batch_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(BillingReconciliation).join(BillingReconciliation.sap_billing).where(
        BillingReconciliation.sap_billing.has(import_batch_id=batch_id))).all()
    counts = {status: sum(1 for row in rows if row.status == status) for status in ("MATCH", "REVIEW", "EXCEPTION", "NOT_FOUND")}
    return {"batch_id": batch_id, "total": len(rows), "counts": counts,
            "rows": [{"id": r.id, "sap_billing_id": r.sap_billing_id, "physical_billing_id": r.physical_billing_id,
                       "billing_match": r.billing_match, "date_match": r.date_match, "nominal_match": r.nominal_match,
                       "nominal_difference": str(r.nominal_difference), "status": r.status, "exception_code": r.exception_code} for r in rows]}


@app.post("/spj/vouch")
def run_spj_vouching(db: Session = Depends(get_db)):
    rows = vouch_spj(db)
    record_audit(db, entity_type="VOUCHING", entity_id=None, action="SPJ_VOUCHING_RUN",
                 status_to="COMPLETED", metadata={"total": len(rows)})
    db.commit()
    return {"total": len(rows), "results": [{"id": r.id, "billing_id": r.billing_id, "spj_id": r.spj_id,
        "status": r.status, "rule_code": r.rule_code} for r in rows]}


@app.get("/results/{billing_id}")
def get_overall_result(billing_id: int, db: Session = Depends(get_db)):
    try: return overall_result(db, billing_id)
    except ValueError as exc: raise handle_error(exc) from exc


@app.get("/exceptions")
def exceptions(db: Session = Depends(get_db)):
    recs = db.scalars(select(BillingReconciliation).where(BillingReconciliation.status.in_(["EXCEPTION", "REVIEW"]))).all()
    vouches = db.scalars(select(VouchingResult).where(VouchingResult.status.in_(["EXCEPTION", "REVIEW"]))).all()
    return {"total": len(recs) + len(vouches), "reconciliation": [{"id": r.id, "status": r.status, "code": r.exception_code,
        "remarks": r.remarks, "sap_billing_id": r.sap_billing_id} for r in recs],
        "vouching": [{"id": r.id, "status": r.status, "code": r.rule_code, "remarks": r.remarks,
        "billing_id": r.billing_id, "reviewer_id": r.reviewer_id} for r in vouches]}


@app.post("/reviews/vouching/{result_id}")
def review_vouching(result_id: int, status: str, reviewer_id: str, remarks: str | None = None,
                    db: Session = Depends(get_db)):
    result = db.get(VouchingResult, result_id)
    if not result: raise HTTPException(status_code=404, detail="Vouching result not found")
    status = status.upper()
    if status not in {"PASS", "REVIEW", "EXCEPTION"}: raise HTTPException(status_code=400, detail="Invalid review status")
    old_status = result.status
    result.status = status; result.reviewer_id = reviewer_id; result.reviewed_at = func.now(); result.remarks = remarks
    record_audit(db, entity_type="VOUCHING_RESULT", entity_id=result.id, action="REVIEW",
                 actor=reviewer_id, status_from=old_status, status_to=status, remarks=remarks)
    db.commit(); db.refresh(result)
    return {"id": result.id, "status": result.status, "reviewer_id": result.reviewer_id, "remarks": result.remarks}


@app.get("/documents/{document_id}")
def document_evidence(document_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc: raise HTTPException(status_code=404, detail="Document not found")
    physical = db.scalar(select(PhysicalBilling).where(PhysicalBilling.document_id == document_id))
    spj = db.scalar(select(SPJ).where(SPJ.document_id == document_id))
    return {"document_id": doc.id, "file_name": doc.file_name, "file_type": doc.file_type, "document_type": doc.document_type,
            "file_hash": doc.file_hash, "storage_path": doc.storage_path, "uploaded_at": doc.uploaded_at,
            "billing_fields": {"billing_document_raw": physical.billing_document_raw, "billing_document": physical.billing_document,
                "no_spj_raw": physical.no_spj_raw, "no_spj": physical.no_spj, "doc_date": physical.doc_date,
                "nominal": str(physical.nominal) if physical.nominal is not None else None,
                "ocr_confidence": str(physical.ocr_confidence) if physical.ocr_confidence is not None else None} if physical else None,
            "spj_fields": {"no_spj_raw": spj.no_spj_raw, "no_spj": spj.no_spj,
                "ocr_confidence": str(spj.ocr_confidence) if spj.ocr_confidence is not None else None} if spj else None}


@app.get("/documents/{document_id}/content")
def document_content(document_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc: raise HTTPException(status_code=404, detail="Document not found")
    path = Path(doc.storage_path)
    if not path.is_file(): raise HTTPException(status_code=404, detail="Stored document file not found")
    return FileResponse(path, filename=doc.file_name)


@app.get("/audit-trail")
def audit_trail(entity_type: str | None = None, entity_id: int | None = None,
                limit: int = 100, db: Session = Depends(get_db)):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    rows = list_audit_trail(db, entity_type=entity_type, entity_id=entity_id, limit=limit)
    return {"total": len(rows), "entries": [{
        "id": row.id, "entity_type": row.entity_type, "entity_id": row.entity_id,
        "action": row.action, "status_from": row.status_from, "status_to": row.status_to,
        "actor": row.actor, "remarks": row.remarks, "metadata": row.metadata_json,
        "created_at": row.created_at,
    } for row in rows]}


@app.get("/reports/{batch_id}")
def generate_report(batch_id: int, format: str = "xlsx", db: Session = Depends(get_db)):
    try:
        path = build_report(db, batch_id, format)
    except ValueError as exc:
        raise handle_error(exc) from exc
    media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if path.suffix == ".xlsx" else "application/pdf"
    return FileResponse(path, filename=path.name, media_type=media)
