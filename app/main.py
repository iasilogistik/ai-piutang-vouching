from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.audit_service import list_audit_trail, record_audit
from app.auth import CurrentUser, require_roles
from app.database import SessionLocal, engine
from app.models import BillingReconciliation, Document, DocumentControlEvidence, ImportBatch, PhysicalBilling, SPJ, VouchingResult
from app.services.auth_gateway import login_with_password, refresh_access_token
from app.services.bulk_upload_ui import bulk_upload_html
from app.services.bulk_zip import classify_entry, iter_bulk_zip_entries, make_upload
from app.services.reports import build_control_evidence_report, build_report
from app.config import settings
from app.services.combined_upload_ui import combined_upload_html
from app.services.control_evidence_dashboard import build_control_evidence_dashboard
from app.services.control_evidence_review import review_control_evidence
from app.services.control_evidence_store import analyze_and_persist_control_evidence, evidence_payload
from app.services.control_evidence_ui import control_evidence_dashboard_html
from app.services.drive_folder import download_drive_folder_file, is_supported_drive_folder_file, list_google_drive_folder_files
from app.services.drive_import_ui import drive_import_html
from app.services.drive_link import download_drive_link_file
from app.services.login_ui import login_html
from app.services.sap_import import import_sap_upload
from app.services.storage import download_bytes
from app.services.uat_pasuruan_ui import uat_pasuruan_html
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


def _ingest_physical_document(db: Session, upload, *, document_type: str, uploaded_by: str | None,
                              source_mode: str, metadata_extra: dict[str, object] | None = None) -> dict[str, object]:
    doc = save_document(db, upload, document_type=document_type, uploaded_by=uploaded_by)
    metadata = {"document_type": document_type, "file_name": doc.file_name, "file_hash": doc.file_hash,
                "source_mode": source_mode}
    if metadata_extra:
        metadata.update(metadata_extra)
    record_audit(db, entity_type="DOCUMENT", entity_id=doc.id, action="UPLOAD", actor=uploaded_by,
                 status_to="UPLOADED", metadata=metadata)
    analysis = ocr_document(db, doc.id)
    control_evidence = None
    if document_type == "SPJ":
        control_evidence = analyze_and_persist_control_evidence(db, doc.id)
    record_audit(db, entity_type="DOCUMENT", entity_id=doc.id, action="AUTO_EXTRACT",
                 actor=uploaded_by, status_to="EXTRACTED",
                 metadata={"engine": analysis.get("engine"), "confidence": analysis.get("confidence"),
                           "source_mode": source_mode,
                           "control_evidence_review_required": bool(control_evidence and control_evidence.get("review_required")),
                           **(metadata_extra or {})})
    return {"document_id": doc.id, "file_name": doc.file_name, "file_hash": doc.file_hash,
            "document_type": document_type, "analysis": analysis, "control_evidence": control_evidence}


def _ingest_classified_upload(db: Session, upload, *, document_types: list[str], uploaded_by: str | None,
                              source_mode: str, metadata_extra: dict[str, object] | None = None) -> dict[str, object]:
    if document_types == ["BILLING", "SPJ"]:
        billing = _ingest_physical_document(db, upload, document_type="BILLING", uploaded_by=uploaded_by,
                                            source_mode=source_mode,
                                            metadata_extra=metadata_extra)
        upload.file.seek(0)
        spj_meta = {**(metadata_extra or {}), "billing_document_id": billing["document_id"]}
        spj = _ingest_physical_document(db, upload, document_type="SPJ", uploaded_by=uploaded_by,
                                        source_mode=source_mode,
                                        metadata_extra=spj_meta)
        return {"mode": "COMBINED", "status": "SUCCESS", "billing_document_id": billing["document_id"],
                "spj_document_id": spj["document_id"],
                "control_evidence_review_required": bool(spj.get("control_evidence") and spj["control_evidence"].get("review_required"))}

    document_type = document_types[0]
    payload = _ingest_physical_document(db, upload, document_type=document_type, uploaded_by=uploaded_by,
                                        source_mode=source_mode,
                                        metadata_extra=metadata_extra)
    return {"mode": document_type, "status": "SUCCESS",
            "billing_document_id": payload["document_id"] if document_type == "BILLING" else None,
            "spj_document_id": payload["document_id"] if document_type == "SPJ" else None,
            "control_evidence_review_required": bool(payload.get("control_evidence") and payload["control_evidence"].get("review_required"))}


def _process_upload_or_zip(db: Session, upload, *, mode: str, uploaded_by: str | None,
                           source_mode: str, metadata_extra: dict[str, object] | None = None) -> tuple[int, list[dict[str, object]]]:
    suffix = Path(upload.filename).suffix.lower()
    if suffix == ".zip":
        entries = iter_bulk_zip_entries(upload)
        results: list[dict[str, object]] = []
        for entry in entries:
            document_types = classify_entry(entry.source_path, mode)
            if not document_types:
                results.append({"source_path": entry.source_path, "file_name": entry.filename, "mode": mode.upper(),
                                "status": "SKIPPED", "reason": "Unable to classify file as BILLING, SPJ, or COMBINED"})
                continue
            try:
                payload = _ingest_classified_upload(db, make_upload(entry), document_types=document_types,
                                                    uploaded_by=uploaded_by, source_mode=source_mode,
                                                    metadata_extra={**(metadata_extra or {}), "zip_source_path": entry.source_path})
                db.commit()
                results.append({"source_path": entry.source_path, "file_name": entry.filename, **payload})
            except ValueError as item_exc:
                db.rollback()
                results.append({"source_path": entry.source_path, "file_name": entry.filename,
                                "mode": "+".join(document_types), "status": "ERROR", "reason": str(item_exc)})
        return len(entries), results

    document_types = classify_entry(upload.filename, mode)
    if not document_types:
        raise ValueError("Unable to classify downloaded file as BILLING, SPJ, or COMBINED. Use mode BILLING, SPJ, or COMBINED.")
    payload = _ingest_classified_upload(db, upload, document_types=document_types, uploaded_by=uploaded_by,
                                        source_mode=source_mode, metadata_extra=metadata_extra)
    db.commit()
    return 1, [{"source_path": upload.filename, "file_name": upload.filename, **payload}]


def _summary(results: list[dict[str, object]]) -> dict[str, int]:
    return {"success": sum(1 for row in results if row["status"] == "SUCCESS"),
            "skipped": sum(1 for row in results if row["status"] == "SKIPPED"),
            "error": sum(1 for row in results if row["status"] == "ERROR")}


@app.get("/health")
def health() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "healthy"}


@app.get("/login", response_class=HTMLResponse)
def login_ui():
    return HTMLResponse(login_html())


@app.post("/auth/login")
def auth_login(email: str = Form(...), password: str = Form(...)):
    try:
        return login_with_password(email, password)
    except ValueError as exc:
        raise handle_error(exc) from exc


@app.post("/auth/refresh")
def auth_refresh(refresh_token: str = Form(...)):
    try:
        return refresh_access_token(refresh_token)
    except ValueError as exc:
        raise handle_error(exc) from exc


@app.get("/auth/me")
def auth_me(user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    return {"user_id": user.user_id, "role": user.role}


@app.get("/ui/control-evidence", response_class=HTMLResponse)
def control_evidence_ui():
    return HTMLResponse(control_evidence_dashboard_html())


@app.get("/ui/combined-upload", response_class=HTMLResponse)
def combined_upload_ui():
    return HTMLResponse(combined_upload_html())


@app.get("/ui/bulk-upload", response_class=HTMLResponse)
def bulk_upload_ui():
    return HTMLResponse(bulk_upload_html())


@app.get("/ui/drive-import", response_class=HTMLResponse)
def drive_import_ui():
    return HTMLResponse(drive_import_html())


@app.get("/ui/uat-pasuruan", response_class=HTMLResponse)
def uat_pasuruan_ui():
    return HTMLResponse(uat_pasuruan_html())


@app.post("/sap/import")
def sap_import(file: UploadFile = File(...), period: date | None = None,
               db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))) -> dict[str, object]:
    try:
        uploaded_by = user.user_id
        batch = import_sap_upload(db, file, uploaded_by=uploaded_by, period=period)
        record_audit(db, entity_type="IMPORT_BATCH", entity_id=batch.id, action="SAP_IMPORT",
                     actor=uploaded_by, status_to=batch.status, metadata={"file_name": batch.file_name, "total_records": batch.total_records})
        db.commit()
    except ValueError as exc:
        db.rollback(); raise handle_error(exc) from exc
    return {"batch_id": batch.id, "file_name": batch.file_name, "period": batch.period.isoformat() if batch.period else None,
            "total_records": batch.total_records, "status": batch.status}


@app.get("/sap/validate/{batch_id}")
def sap_validate(batch_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    try: return validate_sap_batch(db, batch_id)
    except ValueError as exc: raise handle_error(exc) from exc


@app.post("/documents/drive-folder-import")
def import_drive_folder(url: str = Form(...), mode: str = Form("AUTO"), db: Session = Depends(get_db),
                        user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    try:
        uploaded_by = user.user_id
        files = list_google_drive_folder_files(url)
        results: list[dict[str, object]] = []
        for item in files:
            if not is_supported_drive_folder_file(item):
                results.append({"source_path": item.name, "file_name": item.name, "mode": mode.upper(),
                                "status": "SKIPPED", "reason": "Unsupported Google Drive file type"})
                continue
            try:
                upload = download_drive_folder_file(item)
                _, item_results = _process_upload_or_zip(
                    db,
                    upload,
                    mode=mode,
                    uploaded_by=uploaded_by,
                    source_mode="DRIVE_FOLDER_ZIP" if Path(upload.filename).suffix.lower() == ".zip" else "DRIVE_FOLDER",
                    metadata_extra={"drive_folder_url": url, "drive_file_id": item.file_id, "drive_file_name": item.name},
                )
                for result in item_results:
                    result["source_path"] = f"{item.name}/{result.get('source_path')}" if Path(upload.filename).suffix.lower() == ".zip" else item.name
                    result["file_name"] = result.get("file_name") or item.name
                results.extend(item_results)
            except ValueError as item_exc:
                db.rollback()
                results.append({"source_path": item.name, "file_name": item.name,
                                "mode": mode.upper(), "status": "ERROR", "reason": str(item_exc)})
        return {"source": "GOOGLE_DRIVE_FOLDER", "mode": mode.upper(), "total_entries": len(results),
                "summary": _summary(results), "results": results}
    except ValueError as exc:
        db.rollback(); raise handle_error(exc) from exc


@app.post("/documents/drive-import")
def import_drive_link(url: str = Form(...), mode: str = Form("AUTO"), db: Session = Depends(get_db),
                      user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    try:
        uploaded_by = user.user_id
        upload = download_drive_link_file(url)
        total, results = _process_upload_or_zip(db, upload, mode=mode, uploaded_by=uploaded_by,
                                                source_mode="DRIVE_ZIP" if Path(upload.filename).suffix.lower() == ".zip" else "DRIVE_LINK",
                                                metadata_extra={"drive_source_url": url})
        return {"source": "SHARE_LINK", "file_name": upload.filename, "mode": mode.upper(),
                "total_entries": total, "summary": _summary(results), "results": results}
    except ValueError as exc:
        db.rollback(); raise handle_error(exc) from exc


@app.post("/documents/bulk-zip")
def upload_bulk_zip(file: UploadFile = File(...), mode: str = "AUTO", db: Session = Depends(get_db),
                    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    try:
        uploaded_by = user.user_id
        entries = iter_bulk_zip_entries(file)
        results = []
        for entry in entries:
            document_types = classify_entry(entry.source_path, mode)
            if not document_types:
                results.append({"source_path": entry.source_path, "file_name": entry.filename, "mode": mode.upper(),
                                "status": "SKIPPED", "reason": "Unable to classify file as BILLING, SPJ, or COMBINED"})
                continue
            try:
                payload = _ingest_classified_upload(db, make_upload(entry), document_types=document_types,
                                                    uploaded_by=uploaded_by,
                                                    source_mode="BULK_ZIP_COMBINED" if document_types == ["BILLING", "SPJ"] else "BULK_ZIP",
                                                    metadata_extra={"zip_source_path": entry.source_path})
                db.commit()
                results.append({"source_path": entry.source_path, "file_name": entry.filename, **payload})
            except ValueError as item_exc:
                db.rollback()
                results.append({"source_path": entry.source_path, "file_name": entry.filename,
                                "mode": "+".join(document_types), "status": "ERROR", "reason": str(item_exc)})
    except ValueError as exc:
        db.rollback(); raise handle_error(exc) from exc
    return {"mode": mode.upper(), "total_entries": len(entries), "summary": _summary(results), "results": results}


@app.post("/documents/combined")
def upload_combined_document(file: UploadFile = File(...), db: Session = Depends(get_db),
                             user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    """Upload one file that contains both Billing and SPJ evidence.

    The same uploaded PDF/image is registered twice: once as BILLING and once as
    SPJ. This supports scanned packages where invoice/billing pages and SPJ
    pages are merged into one file. Field matching still uses deterministic
    billing and SPJ rules; unclear OCR remains REVIEW/manual check.
    """
    try:
        uploaded_by = user.user_id
        billing_doc = save_document(db, file, document_type="BILLING", uploaded_by=uploaded_by)
        record_audit(db, entity_type="DOCUMENT", entity_id=billing_doc.id, action="UPLOAD", actor=uploaded_by,
                     status_to="UPLOADED", metadata={"document_type": "BILLING", "file_name": billing_doc.file_name,
                                                     "file_hash": billing_doc.file_hash, "source_mode": "COMBINED"})
        billing_analysis = ocr_document(db, billing_doc.id)
        record_audit(db, entity_type="DOCUMENT", entity_id=billing_doc.id, action="AUTO_EXTRACT",
                     actor=uploaded_by, status_to="EXTRACTED",
                     metadata={"engine": billing_analysis.get("engine"), "confidence": billing_analysis.get("confidence"),
                               "source_mode": "COMBINED"})

        file.file.seek(0)
        spj_doc = save_document(db, file, document_type="SPJ", uploaded_by=uploaded_by)
        record_audit(db, entity_type="DOCUMENT", entity_id=spj_doc.id, action="UPLOAD", actor=uploaded_by,
                     status_to="UPLOADED", metadata={"document_type": "SPJ", "file_name": spj_doc.file_name,
                                                     "file_hash": spj_doc.file_hash, "source_mode": "COMBINED",
                                                     "billing_document_id": billing_doc.id})
        spj_analysis = ocr_document(db, spj_doc.id)
        control_evidence = analyze_and_persist_control_evidence(db, spj_doc.id)
        record_audit(db, entity_type="DOCUMENT", entity_id=spj_doc.id, action="AUTO_EXTRACT",
                     actor=uploaded_by, status_to="EXTRACTED",
                     metadata={"engine": spj_analysis.get("engine"), "confidence": spj_analysis.get("confidence"),
                               "source_mode": "COMBINED", "billing_document_id": billing_doc.id,
                               "control_evidence_review_required": bool(control_evidence and control_evidence.get("review_required"))})
        db.commit()
    except ValueError as exc:
        db.rollback(); raise handle_error(exc) from exc
    return {
        "mode": "COMBINED_BILLING_SPJ",
        "file_name": billing_doc.file_name,
        "billing_document": {"document_id": billing_doc.id, "file_hash": billing_doc.file_hash,
                             "analysis": billing_analysis},
        "spj_document": {"document_id": spj_doc.id, "file_hash": spj_doc.file_hash,
                         "analysis": spj_analysis, "control_evidence": control_evidence},
    }


@app.post("/documents/{document_type}")
def upload_document(document_type: str, file: UploadFile = File(...),
                    db: Session = Depends(get_db),
                    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    document_type = document_type.upper()
    if document_type not in {"BILLING", "SPJ"}:
        raise HTTPException(status_code=400, detail="document_type must be BILLING or SPJ")
    try:
        uploaded_by = user.user_id
        doc = save_document(db, file, document_type=document_type, uploaded_by=uploaded_by)
        record_audit(db, entity_type="DOCUMENT", entity_id=doc.id, action="UPLOAD", actor=uploaded_by,
                     status_to="UPLOADED", metadata={"document_type": document_type, "file_name": doc.file_name, "file_hash": doc.file_hash})
        analysis = ocr_document(db, doc.id)
        control_evidence = None
        if doc.document_type == "SPJ":
            control_evidence = analyze_and_persist_control_evidence(db, doc.id)
        record_audit(db, entity_type="DOCUMENT", entity_id=doc.id, action="AUTO_EXTRACT",
                     actor=uploaded_by, status_to="EXTRACTED",
                     metadata={"engine": analysis.get("engine"), "confidence": analysis.get("confidence"),
                               "control_evidence_review_required": bool(control_evidence and control_evidence.get("review_required"))})
        db.commit()
    except ValueError as exc:
        db.rollback(); raise handle_error(exc) from exc
    return {"document_id": doc.id, "file_name": doc.file_name, "document_type": doc.document_type, "file_hash": doc.file_hash,
            "analysis": analysis, "control_evidence": control_evidence}


@app.post("/documents/{document_id}/ocr")
def run_ocr(document_id: int, db: Session = Depends(get_db),
            user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    try:
        result = ocr_document(db, document_id)
        doc = db.get(Document, document_id)
        control_evidence = None
        if doc and doc.document_type == "SPJ":
            control_evidence = analyze_and_persist_control_evidence(db, document_id)
        record_audit(db, entity_type="DOCUMENT", entity_id=document_id, action="OCR",
                     status_to="OCR_PROCESSED", metadata={"engine": result.get("engine"), "confidence": result.get("confidence"),
                                                           "control_evidence_review_required": bool(control_evidence and control_evidence.get("review_required"))})
        db.commit()
        if control_evidence is not None:
            result["control_evidence"] = control_evidence
        return result
    except ValueError as exc: raise handle_error(exc) from exc


@app.post("/reconciliation/{batch_id}/run")
def run_reconciliation(batch_id: int, db: Session = Depends(get_db),
                       user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    try:
        rows = reconcile_batch(db, batch_id)
        record_audit(db, entity_type="IMPORT_BATCH", entity_id=batch_id, action="RECONCILIATION_RUN",
                     status_to="COMPLETED", metadata={"total": len(rows)})
        db.commit()
    except ValueError as exc: raise handle_error(exc) from exc
    return {"batch_id": batch_id, "total": len(rows), "results": [{"id": r.id, "status": r.status,
        "exception_code": r.exception_code, "nominal_difference": str(r.nominal_difference)} for r in rows]}


@app.get("/reconciliation/{batch_id}")
def reconciliation_dashboard(batch_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    rows = db.scalars(select(BillingReconciliation).join(BillingReconciliation.sap_billing).where(
        BillingReconciliation.sap_billing.has(import_batch_id=batch_id))).all()
    counts = {status: sum(1 for row in rows if row.status == status) for status in ("MATCH", "REVIEW", "EXCEPTION", "NOT_FOUND")}
    return {"batch_id": batch_id, "total": len(rows), "counts": counts,
            "rows": [{"id": r.id, "sap_billing_id": r.sap_billing_id, "physical_billing_id": r.physical_billing_id,
                       "billing_match": r.billing_match, "date_match": r.date_match, "nominal_match": r.nominal_match,
                       "nominal_difference": str(r.nominal_difference), "status": r.status, "exception_code": r.exception_code} for r in rows]}


@app.post("/spj/vouch")
def run_spj_vouching(db: Session = Depends(get_db),
                     user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    rows = vouch_spj(db)
    record_audit(db, entity_type="VOUCHING", entity_id=None, action="SPJ_VOUCHING_RUN",
                 status_to="COMPLETED", metadata={"total": len(rows)})
    db.commit()
    return {"total": len(rows), "results": [{"id": r.id, "billing_id": r.billing_id, "spj_id": r.spj_id,
        "status": r.status, "rule_code": r.rule_code} for r in rows]}


@app.get("/results/{billing_id}")
def get_overall_result(billing_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    try: return overall_result(db, billing_id)
    except ValueError as exc: raise handle_error(exc) from exc


@app.get("/exceptions")
def exceptions(db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    recs = db.scalars(select(BillingReconciliation).where(BillingReconciliation.status.in_(["EXCEPTION", "REVIEW"]))).all()
    vouches = db.scalars(select(VouchingResult).where(VouchingResult.status.in_(["EXCEPTION", "REVIEW"]))).all()
    control_rows = db.scalars(select(DocumentControlEvidence).where(DocumentControlEvidence.review_required == True)).all()  # noqa: E712
    return {"total": len(recs) + len(vouches) + len(control_rows), "reconciliation": [{"id": r.id, "status": r.status, "code": r.exception_code,
        "remarks": r.remarks, "sap_billing_id": r.sap_billing_id} for r in recs],
        "vouching": [{"id": r.id, "status": r.status, "code": r.rule_code, "remarks": r.remarks,
        "billing_id": r.billing_id, "reviewer_id": r.reviewer_id} for r in vouches],
        "control_evidence": [{"id": row.id, "document_id": row.document_id, "review_required": row.review_required,
        "review_status": row.review_status, "reviewer_id": row.reviewer_id, "reviewer_remarks": row.reviewer_remarks,
        "review_reasons": [reason.strip() for reason in (row.review_reasons or "").split(";") if reason.strip()]} for row in control_rows]}


@app.get("/dashboard/control-evidence/export")
def export_control_evidence_dashboard(review_only: bool = False, limit: int = 500,
                                      db: Session = Depends(get_db),
                                      user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    path = build_control_evidence_report(db, review_only=review_only, limit=limit)
    media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(path, filename=path.name, media_type=media)


@app.get("/dashboard/control-evidence")
def control_evidence_dashboard(review_only: bool = False, limit: int = 200,
                               db: Session = Depends(get_db),
                               user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    return build_control_evidence_dashboard(db, review_only=review_only, limit=limit)


@app.post("/reviews/control-evidence/{evidence_id}")
def review_control_evidence_result(evidence_id: int, status: str, remarks: str | None = None,
                                   db: Session = Depends(get_db),
                                   user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER"))):
    try:
        result = review_control_evidence(db, evidence_id, status=status, reviewer_id=user.user_id, remarks=remarks)
        record_audit(
            db,
            entity_type="DOCUMENT_CONTROL_EVIDENCE",
            entity_id=evidence_id,
            action="REVIEW",
            actor=user.user_id,
            status_from=result.get("previous_review_status"),
            status_to=result.get("review_status"),
            remarks=remarks,
            metadata={"document_id": result.get("document_id"), "review_required": result.get("review_required")},
        )
        db.commit()
        return result
    except ValueError as exc:
        db.rollback(); raise handle_error(exc) from exc


@app.post("/reviews/vouching/{result_id}")
def review_vouching(result_id: int, status: str, remarks: str | None = None,
                    db: Session = Depends(get_db),
                    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER"))):
    reviewer_id = user.user_id
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
def document_evidence(document_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    doc = db.get(Document, document_id)
    if not doc: raise HTTPException(status_code=404, detail="Document not found")
    physical = db.scalar(select(PhysicalBilling).where(PhysicalBilling.document_id == document_id))
    spj = db.scalar(select(SPJ).where(SPJ.document_id == document_id))
    control = db.scalar(select(DocumentControlEvidence).where(DocumentControlEvidence.document_id == document_id))
    return {
        "document_id": doc.id, "file_name": doc.file_name, "file_type": doc.file_type, "document_type": doc.document_type,
        "file_hash": doc.file_hash, "storage_path": doc.storage_path, "uploaded_at": doc.uploaded_at,
        "billing_fields": {
            "billing_document_raw": physical.billing_document_raw, "billing_document": physical.billing_document,
            "no_spj_raw": physical.no_spj_raw, "no_spj": physical.no_spj, "doc_date": physical.doc_date,
            "nominal": str(physical.nominal) if physical.nominal is not None else None,
            "partial_payment_raw": physical.partial_payment_raw,
            "partial_payment": str(physical.partial_payment) if physical.partial_payment is not None else None,
            "ocr_confidence": str(physical.ocr_confidence) if physical.ocr_confidence is not None else None,
        } if physical else None,
        "spj_fields": {
            "no_spj_raw": spj.no_spj_raw, "no_spj": spj.no_spj,
            "partial_payment_raw": spj.partial_payment_raw,
            "partial_payment": str(spj.partial_payment) if spj.partial_payment is not None else None,
            "ocr_confidence": str(spj.ocr_confidence) if spj.ocr_confidence is not None else None,
        } if spj else None,
        "control_evidence": evidence_payload(control),
    }


@app.get("/documents/{document_id}/content")
def document_content(document_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    doc = db.get(Document, document_id)
    if not doc: raise HTTPException(status_code=404, detail="Document not found")
    if settings.use_supabase_storage:
        try:
            content = download_bytes(doc.storage_path)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        media = "application/pdf" if doc.file_type == "PDF" else f"image/{doc.file_type.lower()}"
        return Response(content=content, media_type=media, headers={"Content-Disposition": f'inline; filename="{doc.file_name}"'})
    path = Path(doc.storage_path)
    if not path.is_file(): raise HTTPException(status_code=404, detail="Stored document file not found")
    return FileResponse(path, filename=doc.file_name)


@app.get("/audit-trail")
def audit_trail(entity_type: str | None = None, entity_id: int | None = None,
                limit: int = 100, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
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
def generate_report(batch_id: int, format: str = "xlsx", db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    try:
        path = build_report(db, batch_id, format)
    except ValueError as exc:
        raise handle_error(exc) from exc
    media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if path.suffix == ".xlsx" else "application/pdf"
    return FileResponse(path, filename=path.name, media_type=media)
