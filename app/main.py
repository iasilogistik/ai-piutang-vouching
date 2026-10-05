from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.audit_service import list_audit_trail, record_audit
from app.auth import CurrentUser, require_roles
from app.branch_access import ensure_branch_access, normalize_branch, scoped_branch, write_branch
from app.database import SessionLocal, engine
from app.models import BillingReconciliation, ControlEvidenceDetection, Document, DocumentControlEvidence, ImportBatch, PhysicalBilling, SAPBilling, SPJ, VouchingResult
from app.services.auth_gateway import login_with_password, refresh_access_token
from app.services.audit_trail_ui import register_audit_trail_ui_routes
from app.services.audit_workflow import register_audit_workflow_routes
from app.services.audit_engagement import register_audit_engagement_routes
from app.services.audit_sampling import register_audit_sampling_routes
from app.services.audit_working_paper import register_audit_working_paper_routes
from app.services.audit_finding import register_audit_finding_routes
from app.services.management_actions import register_management_action_routes
from app.services.follow_up import register_follow_up_routes
from app.services.audit_report import register_audit_report_routes
from app.services.audit_closing import register_audit_closing_routes
from app.services.branch_dashboard import register_branch_dashboard_routes
from app.services.branch_master import ensure_branch_catalog
from app.services.audit_management_dashboard import register_audit_management_dashboard_routes
from app.services.bulk_upload_ui import bulk_upload_html
from app.services.bulk_zip import classify_entry, iter_bulk_zip_entries, make_upload
from app.services.review_workflow import register_review_workflow_routes
from app.services.reviewer_center import register_reviewer_center_routes
from app.services.viewer_center import register_viewer_center_routes
from app.config import settings
from app.services.combined_upload_ui import combined_upload_html
from app.services.control_evidence_dashboard import build_control_evidence_dashboard
from app.services.control_evidence_review import review_control_evidence
from app.services.control_evidence_store import analyze_and_persist_control_evidence, evidence_payload
from app.services.control_evidence_ui import control_evidence_dashboard_html
from app.services.drive_folder import download_drive_folder_file, is_supported_drive_folder_file, list_google_drive_folder_files
from app.services.drive_import_ui import drive_import_html
from app.services.drive_link import download_drive_link_file
from app.services.document_viewer import register_document_viewer_routes
from app.services.exception_management import register_exception_management_routes
from app.services.evidence_repository import register_evidence_repository_routes
from app.services.global_search import register_global_search_routes
from app.services.login_ui import login_html
from app.services.navigation import register_navigation_routes
from app.services.notifications import register_notification_routes
from app.services.release_readiness import register_release_readiness_routes
from app.services.sap_import import import_sap_upload
from app.services.storage import download_bytes, upload_bytes
from app.services.uat_pasuruan_ui import uat_pasuruan_html
from app.services.upload_center import register_upload_center_routes
from app.services.reconciliation_vouching_ui import register_reconciliation_vouching_routes
from app.services.upload_management import router as upload_management_router
from app.services.user_management import register_user_management_routes
from app.services.vouching import _normalize_spj_number, confirm_reconciliation_manual, ocr_document, overall_result, reconcile_batch, review_vouching_result, save_document, validate_sap_batch, vouch_spj

app = FastAPI(title="AI Piutang Vouching")
app.include_router(upload_management_router)

_UI_SHELL_EXEMPT_PATHS = {"/ui/main", "/ui/navigation"}


@app.middleware("http")
async def keep_browser_ui_inside_persistent_shell(request: Request, call_next):
    path = request.url.path
    fetch_dest = (request.headers.get("sec-fetch-dest") or "").strip().lower()
    is_top_level_browser_navigation = fetch_dest == "document"
    if (
        request.method == "GET"
        and is_top_level_browser_navigation
        and path.startswith("/ui/")
        and path not in _UI_SHELL_EXEMPT_PATHS
    ):
        target = path
        if request.url.query:
            target += "?" + request.url.query
        return RedirectResponse(
            url="/ui/main?view=" + quote(target, safe=""),
            status_code=307,
        )
    return await call_next(request)


register_release_readiness_routes(app)
register_user_management_routes(app)
register_navigation_routes(app)
register_notification_routes(app)
register_branch_dashboard_routes(app)
register_audit_management_dashboard_routes(app)
register_upload_center_routes(app)
register_reconciliation_vouching_routes(app)
register_exception_management_routes(app)
register_evidence_repository_routes(app)
register_global_search_routes(app)
register_review_workflow_routes(app)
register_reviewer_center_routes(app)
register_viewer_center_routes(app)
register_document_viewer_routes(app)
register_audit_trail_ui_routes(app)
register_audit_report_routes(app)
register_audit_closing_routes(app)
register_audit_workflow_routes(app)
register_audit_engagement_routes(app)
register_audit_sampling_routes(app)
register_audit_working_paper_routes(app)
register_audit_finding_routes(app)
register_management_action_routes(app)
register_follow_up_routes(app)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def handle_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _prepare_upload_branch(db: Session, user: CurrentUser, branch: str | None) -> str:
    resolved = write_branch(user, branch)
    return ensure_branch_catalog(db, resolved)


def _sap_requested_branch(user: CurrentUser, branch: str | None) -> str | None:
    assigned = normalize_branch(user.branch)
    if assigned is not None:
        return write_branch(user, branch)
    return normalize_branch(branch)


def _document_for_user(db: Session, document_id: int, user: CurrentUser) -> Document:
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    ensure_branch_access(user, doc.branch)
    return doc


def _batch_for_user(db: Session, batch_id: int, user: CurrentUser) -> ImportBatch:
    batch = db.get(ImportBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="SAP import batch not found")
    ensure_branch_access(user, batch.branch)
    return batch


def _ingest_physical_document(db: Session, upload, *, document_type: str, uploaded_by: str | None,
                              source_mode: str, branch: str | None = None,
                              metadata_extra: dict[str, object] | None = None) -> dict[str, object]:
    incoming_name = Path(upload.filename or "document").name
    normalized_branch = normalize_branch(branch)
    previous_query = (
        select(Document)
        .where(
            Document.document_type == document_type,
            Document.file_name == incoming_name,
            Document.archived_at.is_(None),
        )
        .order_by(Document.evidence_version_number.desc(), Document.id.desc())
    )
    previous_query = previous_query.where(
        Document.branch == normalized_branch if normalized_branch is not None else Document.branch.is_(None)
    )
    previous = db.scalar(previous_query)

    doc = save_document(db, upload, document_type=document_type, uploaded_by=uploaded_by, branch=branch)
    ingest_action = "ADDED"
    if previous is not None and previous.id != doc.id:
        ingest_action = "REPLACED"
        doc.supersedes_document_id = previous.id
        doc.evidence_version_number = max(int(previous.evidence_version_number or 1) + 1, 2)
        previous.archived_at = datetime.now(timezone.utc)
        previous.archived_by = uploaded_by
        previous.archive_reason = f"Replaced by evidence document {doc.id} from {source_mode}"
        record_audit(
            db,
            entity_type="DOCUMENT",
            entity_id=previous.id,
            action="EVIDENCE_REPLACED",
            actor=uploaded_by,
            status_from="ACTIVE",
            status_to="ARCHIVED",
            metadata={"replacement_document_id": doc.id, "file_name": incoming_name, "source_mode": source_mode},
            branch=previous.branch,
        )
        db.flush()

    metadata = {"document_type": document_type, "file_name": doc.file_name, "file_hash": doc.file_hash,
                "source_mode": source_mode, "ingest_action": ingest_action,
                "supersedes_document_id": doc.supersedes_document_id,
                "evidence_version_number": doc.evidence_version_number}
    if metadata_extra:
        metadata.update(metadata_extra)
    record_audit(db, entity_type="DOCUMENT", entity_id=doc.id, action="UPLOAD", actor=uploaded_by,
                 status_to="UPLOADED", metadata=metadata, branch=doc.branch)
    analysis = ocr_document(db, doc.id)
    control_evidence = None
    if document_type == "SPJ":
        if analysis.get("vision"):
            control_evidence = analyze_and_persist_control_evidence(
                db,
                doc.id,
                vision_result=analysis.get("vision"),
            )
        else:
            control_evidence = analyze_and_persist_control_evidence(db, doc.id)
    record_audit(db, entity_type="DOCUMENT", entity_id=doc.id, action="AUTO_EXTRACT",
                 actor=uploaded_by, status_to="EXTRACTED",
                 metadata={"engine": analysis.get("engine"), "confidence": analysis.get("confidence"),
                           "source_mode": source_mode,
                           "control_evidence_review_required": bool(control_evidence and control_evidence.get("review_required")),
                           **(metadata_extra or {})}, branch=doc.branch)
    return {"document_id": doc.id, "file_name": doc.file_name, "file_hash": doc.file_hash,
            "document_type": document_type, "analysis": analysis, "control_evidence": control_evidence,
            "ingest_action": ingest_action, "supersedes_document_id": doc.supersedes_document_id,
            "evidence_version_number": doc.evidence_version_number}


def _ingest_classified_upload(db: Session, upload, *, document_types: list[str], uploaded_by: str | None,
                              source_mode: str, branch: str | None = None,
                              metadata_extra: dict[str, object] | None = None) -> dict[str, object]:
    if document_types == ["BILLING", "SPJ"]:
        billing = _ingest_physical_document(db, upload, document_type="BILLING", uploaded_by=uploaded_by,
                                            source_mode=source_mode, branch=branch,
                                            metadata_extra=metadata_extra)
        upload.file.seek(0)
        spj_meta = {**(metadata_extra or {}), "billing_document_id": billing["document_id"]}
        spj = _ingest_physical_document(db, upload, document_type="SPJ", uploaded_by=uploaded_by,
                                        source_mode=source_mode, branch=branch,
                                        metadata_extra=spj_meta)
        return {"mode": "COMBINED", "status": "SUCCESS", "billing_document_id": billing["document_id"],
                "spj_document_id": spj["document_id"],
                "ingest_action": "REPLACED" if "REPLACED" in {billing["ingest_action"], spj["ingest_action"]} else "ADDED",
                "billing_ingest_action": billing["ingest_action"], "spj_ingest_action": spj["ingest_action"],
                "control_evidence_review_required": bool(spj.get("control_evidence") and spj["control_evidence"].get("review_required"))}

    document_type = document_types[0]
    payload = _ingest_physical_document(db, upload, document_type=document_type, uploaded_by=uploaded_by,
                                        source_mode=source_mode, branch=branch,
                                        metadata_extra=metadata_extra)
    return {"mode": document_type, "status": "SUCCESS", "ingest_action": payload["ingest_action"],
            "supersedes_document_id": payload["supersedes_document_id"],
            "evidence_version_number": payload["evidence_version_number"],
            "billing_document_id": payload["document_id"] if document_type == "BILLING" else None,
            "spj_document_id": payload["document_id"] if document_type == "SPJ" else None,
            "control_evidence_review_required": bool(payload.get("control_evidence") and payload["control_evidence"].get("review_required"))}


def _process_upload_or_zip(db: Session, upload, *, mode: str, uploaded_by: str | None,
                           source_mode: str, branch: str | None = None,
                           metadata_extra: dict[str, object] | None = None) -> tuple[int, list[dict[str, object]]]:
    suffix = Path(upload.filename).suffix.lower()
    if suffix in {".zip", ".rar"}:
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
                                                    uploaded_by=uploaded_by, source_mode=source_mode, branch=branch,
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
                                        source_mode=source_mode, branch=branch, metadata_extra=metadata_extra)
    db.commit()
    return 1, [{"source_path": upload.filename, "file_name": upload.filename, **payload}]


def _summary(results: list[dict[str, object]]) -> dict[str, int]:
    return {"success": sum(1 for row in results if row["status"] == "SUCCESS"),
            "added": sum(1 for row in results if row.get("status") == "SUCCESS" and row.get("ingest_action") == "ADDED"),
            "replaced": sum(1 for row in results if row.get("status") == "SUCCESS" and row.get("ingest_action") == "REPLACED"),
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
    return {"user_id": user.user_id, "role": user.role, "branch": user.branch,
            "access_scope": "ALL" if user.role == "ADMIN" else scoped_branch(user)}


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
def sap_import(file: UploadFile = File(...), period: date | None = None, branch: str | None = None,
               db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))) -> dict[str, object]:
    try:
        uploaded_by = user.user_id
        target_branch = _sap_requested_branch(user, branch)
        batch = import_sap_upload(db, file, uploaded_by=uploaded_by, period=period, branch=target_branch)
        record_audit(db, entity_type="IMPORT_BATCH", entity_id=batch.id, action="SAP_IMPORT",
                     actor=uploaded_by, status_to=batch.status, metadata={"file_name": batch.file_name, "total_records": batch.total_records},
                     branch=batch.branch)
        db.commit()
    except ValueError as exc:
        db.rollback(); raise handle_error(exc) from exc
    return {"batch_id": batch.id, "file_name": batch.file_name, "period": batch.period.isoformat() if batch.period else None,
            "total_records": batch.total_records, "status": batch.status, "branch": batch.branch}


@app.get("/sap/validate/{batch_id}")
def sap_validate(batch_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    try: return validate_sap_batch(db, batch_id, branch=scoped_branch(user))
    except ValueError as exc: raise handle_error(exc) from exc


@app.post("/documents/drive-folder-import")
def import_drive_folder(url: str = Form(...), mode: str = Form("AUTO"), branch: str | None = Form(None),
                        db: Session = Depends(get_db),
                        user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    try:
        uploaded_by = user.user_id
        target_branch = _prepare_upload_branch(db, user, branch)
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
                    branch=target_branch,
                    source_mode="DRIVE_FOLDER_ARCHIVE" if Path(upload.filename).suffix.lower() in {".zip", ".rar"} else "DRIVE_FOLDER",
                    metadata_extra={"drive_folder_url": url, "drive_file_id": item.file_id, "drive_file_name": item.name},
                )
                for result in item_results:
                    result["source_path"] = f"{item.name}/{result.get('source_path')}" if Path(upload.filename).suffix.lower() in {".zip", ".rar"} else item.name
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
def import_drive_link(url: str = Form(...), mode: str = Form("AUTO"), branch: str | None = Form(None),
                      db: Session = Depends(get_db),
                      user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    try:
        uploaded_by = user.user_id
        target_branch = _prepare_upload_branch(db, user, branch)
        upload = download_drive_link_file(url)
        total, results = _process_upload_or_zip(db, upload, mode=mode, uploaded_by=uploaded_by, branch=target_branch,
                                                source_mode="DRIVE_ARCHIVE" if Path(upload.filename).suffix.lower() in {".zip", ".rar"} else "DRIVE_LINK",
                                                metadata_extra={"drive_source_url": url})
        return {"source": "SHARE_LINK", "file_name": upload.filename, "mode": mode.upper(),
                "total_entries": total, "summary": _summary(results), "results": results}
    except ValueError as exc:
        db.rollback(); raise handle_error(exc) from exc


@app.post("/documents/bulk-archive")
@app.post("/documents/bulk-zip")
def upload_bulk_zip(file: UploadFile = File(...), mode: str = "AUTO", branch: str | None = None,
                    db: Session = Depends(get_db),
                    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    try:
        uploaded_by = user.user_id
        target_branch = _prepare_upload_branch(db, user, branch)
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
                                                    uploaded_by=uploaded_by, branch=target_branch,
                                                    source_mode="BULK_ARCHIVE_COMBINED" if document_types == ["BILLING", "SPJ"] else "BULK_ARCHIVE",
                                                    metadata_extra={"archive_source_path": entry.source_path, "archive_type": Path(file.filename or "").suffix.lower().lstrip(".").upper()})
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
def upload_combined_document(file: UploadFile = File(...), branch: str | None = None,
                             db: Session = Depends(get_db),
                             user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    """Upload one file that contains both Billing and SPJ evidence.

    The same uploaded PDF/image is registered twice: once as BILLING and once as
    SPJ. This supports scanned packages where invoice/billing pages and SPJ
    pages are merged into one file. Field matching still uses deterministic
    billing and SPJ rules; unclear OCR remains REVIEW/manual check.
    """
    try:
        uploaded_by = user.user_id
        target_branch = _prepare_upload_branch(db, user, branch)
        billing_doc = save_document(db, file, document_type="BILLING", uploaded_by=uploaded_by, branch=target_branch)
        record_audit(db, entity_type="DOCUMENT", entity_id=billing_doc.id, action="UPLOAD", actor=uploaded_by,
                     status_to="UPLOADED", metadata={"document_type": "BILLING", "file_name": billing_doc.file_name,
                                                     "file_hash": billing_doc.file_hash, "source_mode": "COMBINED"},
                     branch=billing_doc.branch)
        billing_analysis = ocr_document(db, billing_doc.id)
        record_audit(db, entity_type="DOCUMENT", entity_id=billing_doc.id, action="AUTO_EXTRACT",
                     actor=uploaded_by, status_to="EXTRACTED",
                     metadata={"engine": billing_analysis.get("engine"), "confidence": billing_analysis.get("confidence"),
                               "source_mode": "COMBINED"}, branch=billing_doc.branch)

        file.file.seek(0)
        spj_doc = save_document(db, file, document_type="SPJ", uploaded_by=uploaded_by, branch=target_branch)
        record_audit(db, entity_type="DOCUMENT", entity_id=spj_doc.id, action="UPLOAD", actor=uploaded_by,
                     status_to="UPLOADED", metadata={"document_type": "SPJ", "file_name": spj_doc.file_name,
                                                     "file_hash": spj_doc.file_hash, "source_mode": "COMBINED",
                                                     "billing_document_id": billing_doc.id}, branch=spj_doc.branch)
        spj_analysis = ocr_document(db, spj_doc.id)
        control_evidence = analyze_and_persist_control_evidence(db, spj_doc.id)
        record_audit(db, entity_type="DOCUMENT", entity_id=spj_doc.id, action="AUTO_EXTRACT",
                     actor=uploaded_by, status_to="EXTRACTED",
                     metadata={"engine": spj_analysis.get("engine"), "confidence": spj_analysis.get("confidence"),
                               "source_mode": "COMBINED", "billing_document_id": billing_doc.id,
                               "control_evidence_review_required": bool(control_evidence and control_evidence.get("review_required"))},
                     branch=spj_doc.branch)
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
def upload_document(document_type: str, file: UploadFile = File(...), branch: str | None = None,
                    db: Session = Depends(get_db),
                    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    document_type = document_type.upper()
    if document_type not in {"BILLING", "SPJ"}:
        raise HTTPException(status_code=400, detail="document_type must be BILLING or SPJ")
    try:
        uploaded_by = user.user_id
        target_branch = _prepare_upload_branch(db, user, branch)
        doc = save_document(db, file, document_type=document_type, uploaded_by=uploaded_by, branch=target_branch)
        record_audit(db, entity_type="DOCUMENT", entity_id=doc.id, action="UPLOAD", actor=uploaded_by,
                     status_to="UPLOADED", metadata={"document_type": document_type, "file_name": doc.file_name, "file_hash": doc.file_hash},
                     branch=doc.branch)
        analysis = ocr_document(db, doc.id)
        control_evidence = None
        if doc.document_type == "SPJ":
            control_evidence = analyze_and_persist_control_evidence(db, doc.id)
        record_audit(db, entity_type="DOCUMENT", entity_id=doc.id, action="AUTO_EXTRACT",
                     actor=uploaded_by, status_to="EXTRACTED",
                     metadata={"engine": analysis.get("engine"), "confidence": analysis.get("confidence"),
                               "control_evidence_review_required": bool(control_evidence and control_evidence.get("review_required"))},
                     branch=doc.branch)
        db.commit()
    except ValueError as exc:
        db.rollback(); raise handle_error(exc) from exc
    return {"document_id": doc.id, "file_name": doc.file_name, "document_type": doc.document_type, "file_hash": doc.file_hash,
            "analysis": analysis, "control_evidence": control_evidence}


@app.post("/documents/{document_id}/ocr")
def run_ocr(document_id: int, db: Session = Depends(get_db),
            user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    try:
        doc = _document_for_user(db, document_id, user)
        result = ocr_document(db, document_id)
        control_evidence = None
        if doc and doc.document_type == "SPJ":
            control_evidence = analyze_and_persist_control_evidence(db, document_id)
        record_audit(db, entity_type="DOCUMENT", entity_id=document_id, action="OCR", actor=user.user_id,
                     status_to="OCR_PROCESSED", metadata={"engine": result.get("engine"), "confidence": result.get("confidence"),
                                                           "control_evidence_review_required": bool(control_evidence and control_evidence.get("review_required"))},
                     branch=doc.branch)
        db.commit()
        if control_evidence is not None:
            result["control_evidence"] = control_evidence
        return result
    except ValueError as exc: raise handle_error(exc) from exc


def _reconciliation_evidence_state_values(
    *,
    status: str | None,
    exception_code: str | None,
    physical_billing_id: int | None,
    remarks: str | None,
) -> str:
    text_value = remarks or ""
    if exception_code == "BILLING_DOCUMENT_NOT_FOUND" or physical_billing_id is None:
        return "BILLING_BELUM_LENGKAP"
    if "Evidence SPJ tersedia" in text_value:
        return "SPJ_OCR_INFO" if status == "MATCH" else "SPJ_OCR_REVIEW"
    if "SPJ belum lengkap" in text_value:
        return "SPJ_BELUM_LENGKAP"
    if "SPJ perlu review" in text_value:
        return "SPJ_PERLU_REVIEW"
    if "Billing belum lengkap" in text_value:
        return "BILLING_BELUM_LENGKAP"
    return "LENGKAP"


def _reconciliation_row_payload(row: BillingReconciliation) -> dict:
    sap = row.sap_billing
    physical = row.physical_billing
    evidence_state = _reconciliation_evidence_state_values(
        status=row.status,
        exception_code=row.exception_code,
        physical_billing_id=row.physical_billing_id,
        remarks=row.remarks,
    )
    return {
        "id": row.id,
        "sap_billing_id": row.sap_billing_id,
        "physical_billing_id": row.physical_billing_id,
        "billing_document": sap.billing_document if sap else None,
        "customer": (sap.customer_account_name or sap.customer) if sap else None,
        "spj_number": physical.no_spj if physical else None,
        "billing_match": row.billing_match,
        "date_match": row.date_match,
        "nominal_match": row.nominal_match,
        "nominal_difference": str(row.nominal_difference),
        "billing_partial_payment": str(physical.partial_payment) if physical and physical.partial_payment is not None else None,
        "billing_partial_payment_raw": physical.partial_payment_raw if physical else None,
        "status": row.status,
        "exception_code": row.exception_code,
        "remarks": row.remarks,
        "evidence_state": evidence_state,
    }


@app.post("/reconciliation/{batch_id}/run")
def run_reconciliation(batch_id: int, db: Session = Depends(get_db),
                       user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    try:
        batch = _batch_for_user(db, batch_id, user)
        rows = reconcile_batch(db, batch_id, branch=scoped_branch(user))
        record_audit(db, entity_type="IMPORT_BATCH", entity_id=batch_id, action="RECONCILIATION_RUN",
                     actor=user.user_id, status_to="COMPLETED", metadata={"total": len(rows)},
                     branch=batch.branch)
        db.commit()
    except ValueError as exc: raise handle_error(exc) from exc
    return {"batch_id": batch_id, "total": len(rows), "results": [_reconciliation_row_payload(r) for r in rows]}


@app.get("/reconciliation/{batch_id}/visual-refresh-candidates")
def reconciliation_visual_refresh_candidates(
    batch_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    batch = _batch_for_user(db, batch_id, user)
    branch = normalize_branch(batch.branch)
    recs = db.scalars(
        select(BillingReconciliation)
        .join(BillingReconciliation.sap_billing)
        .where(SAPBilling.import_batch_id == batch_id)
        .order_by(BillingReconciliation.id)
    ).all()

    items = []
    seen: set[int] = set()
    for rec in recs:
        if rec.physical_billing_id is None:
            continue
        billing = db.get(PhysicalBilling, rec.physical_billing_id)
        if billing is None or billing.document is None:
            continue
        bill_doc = billing.document
        spj_query = (
            select(SPJ)
            .join(SPJ.document)
            .where(
                Document.document_type == "SPJ",
                Document.file_hash == bill_doc.file_hash,
                Document.file_name == bill_doc.file_name,
                Document.archived_at.is_(None),
            )
        )
        spj_query = spj_query.where(
            Document.branch == branch if branch is not None else Document.branch.is_(None)
        )
        paired = list(db.scalars(spj_query).all())
        if len(paired) != 1:
            continue
        spj = paired[0]
        if spj.document_id in seen:
            continue
        seen.add(spj.document_id)

        current_v15 = db.scalar(
            select(ControlEvidenceDetection.id).where(
                ControlEvidenceDetection.document_id == spj.document_id,
                ControlEvidenceDetection.extraction_engine.contains("LOCAL_TESSERACT_VISUAL_V15"),
            ).limit(1)
        )
        malformed_spj = bool(spj.no_spj and _normalize_spj_number(spj.no_spj) is None)
        if current_v15 is not None and not malformed_spj:
            continue

        control = db.scalar(
            select(DocumentControlEvidence).where(
                DocumentControlEvidence.document_id == spj.document_id
            )
        )
        items.append(
            {
                "document_id": spj.document_id,
                "file_name": spj.document.file_name,
                "spj_id": spj.id,
                "billing_id": billing.id,
                "reconciliation_id": rec.id,
                "current_review_required": bool(control.review_required) if control else True,
            }
        )
    return {"batch_id": batch_id, "branch": batch.branch, "total": len(items), "items": items}


@app.post("/control-evidence/{document_id}/reanalyze-visual")
def reanalyze_control_evidence_visual(
    document_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    doc = db.get(Document, document_id)
    if doc is None or doc.document_type != "SPJ" or doc.archived_at is not None:
        raise HTTPException(status_code=404, detail="SPJ evidence tidak ditemukan.")
    ensure_branch_access(user, doc.branch)

    paired_query = (
        select(PhysicalBilling)
        .join(PhysicalBilling.document)
        .where(
            Document.document_type == "BILLING",
            Document.file_hash == doc.file_hash,
            Document.file_name == doc.file_name,
            Document.archived_at.is_(None),
        )
    )
    branch = normalize_branch(doc.branch)
    paired_query = paired_query.where(
        Document.branch == branch if branch is not None else Document.branch.is_(None)
    )
    billings = list(db.scalars(paired_query).all())
    billing = billings[0] if len(billings) == 1 else None

    sap = None
    if billing is not None:
        rec = db.scalar(
            select(BillingReconciliation)
            .where(BillingReconciliation.physical_billing_id == billing.id)
            .order_by(BillingReconciliation.id.desc())
        )
        if rec is not None:
            sap = db.get(SAPBilling, rec.sap_billing_id)

    expected_customer = (
        (sap.customer_account_name or sap.customer)
        if sap is not None
        else None
    )
    analysis = ocr_document(
        db,
        document_id,
        expected_customer=expected_customer,
        expected_billing_document=sap.billing_document if sap else (billing.billing_document if billing else None),
        expected_nominal=sap.nominal if sap else None,
        expected_doc_date=sap.doc_date if sap else None,
        force_vision=True,
    )
    payload = analyze_and_persist_control_evidence(
        db,
        document_id,
        expected_customer=expected_customer,
        vision_result=analysis.get("vision"),
        ocr_text=analysis.get("ocr_text"),
        ocr_engine=analysis.get("engine"),
    )
    record_audit(
        db,
        entity_type="DOCUMENT",
        entity_id=document_id,
        action="VISUAL_EVIDENCE_REANALYZE",
        actor=user.user_id,
        status_to=payload.get("review_status") or ("REVIEW" if payload.get("review_required") else "PASS"),
        metadata={
            "file_name": doc.file_name,
            "engine": payload.get("engine"),
            "vision_used": payload.get("vision_used"),
            "expected_customer": expected_customer,
        },
        branch=doc.branch,
    )
    db.commit()
    return {
        "document_id": document_id,
        "file_name": doc.file_name,
        "ocr": analysis,
        "control_evidence": payload,
    }


@app.post("/reconciliation/results/{reconciliation_id}/confirm-manual")
def confirm_reconciliation_result_manual(
    reconciliation_id: int,
    confirmed: bool = False,
    remarks: str | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER")),
):
    if not confirmed:
        raise HTTPException(
            status_code=400,
            detail=(
                "Konfirmasi manual wajib menyatakan Billing, tanggal/nominal, SPJ, "
                "tanda tangan, dan stempel telah diperiksa dan sesuai."
            ),
        )
    before = db.get(BillingReconciliation, reconciliation_id)
    before_status = before.status if before else None
    try:
        payload = confirm_reconciliation_manual(
            db,
            reconciliation_id,
            reviewer_id=user.user_id,
            remarks=remarks,
            branch=scoped_branch(user),
        )
        billing = db.get(PhysicalBilling, payload["physical_billing_id"])
        record_audit(
            db,
            entity_type="BILLING_RECONCILIATION",
            entity_id=reconciliation_id,
            action="MANUAL_CONFIRM_MATCH",
            actor=user.user_id,
            status_from=before_status,
            status_to="MATCH",
            remarks=payload.get("remarks"),
            metadata={
                "sap_billing_id": payload.get("sap_billing_id"),
                "physical_billing_id": payload.get("physical_billing_id"),
                "spj_id": payload.get("spj_id"),
                "vouching_result_id": payload.get("vouching_result_id"),
                "control_evidence_id": payload.get("control_evidence_id"),
                "manual_confirmed": True,
            },
            branch=billing.document.branch if billing and billing.document else scoped_branch(user),
        )
        db.commit()
        return payload
    except ValueError as exc:
        db.rollback()
        raise handle_error(exc) from exc


@app.post("/reconciliation/{batch_id}/confirm-manual-review")
def confirm_reconciliation_batch_manual(
    batch_id: int,
    confirmed: bool = False,
    remarks: str | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER")),
):
    if not confirmed:
        raise HTTPException(
            status_code=400,
            detail="Konfirmasi batch wajib mencentang pernyataan pemeriksaan manual.",
        )
    batch = _batch_for_user(db, batch_id, user)
    rows = db.scalars(
        select(BillingReconciliation)
        .join(BillingReconciliation.sap_billing)
        .where(
            BillingReconciliation.sap_billing.has(import_batch_id=batch_id),
            BillingReconciliation.status == "REVIEW",
            BillingReconciliation.physical_billing_id.is_not(None),
        )
        .order_by(BillingReconciliation.id)
    ).all()
    confirmed_rows = []
    skipped = []
    for row in rows:
        try:
            payload = confirm_reconciliation_manual(
                db,
                row.id,
                reviewer_id=user.user_id,
                remarks=remarks,
                branch=scoped_branch(user),
            )
            confirmed_rows.append(payload)
        except ValueError as exc:
            skipped.append({"reconciliation_id": row.id, "reason": str(exc)})

    record_audit(
        db,
        entity_type="IMPORT_BATCH",
        entity_id=batch_id,
        action="MANUAL_CONFIRM_REVIEW_BATCH",
        actor=user.user_id,
        status_from=None,
        status_to="CONFIRMED",
        remarks=remarks,
        metadata={
            "confirmed_count": len(confirmed_rows),
            "skipped_count": len(skipped),
            "confirmed_ids": [row["reconciliation_id"] for row in confirmed_rows],
            "skipped": skipped,
        },
        branch=batch.branch,
    )
    db.commit()
    return {
        "batch_id": batch_id,
        "confirmed_count": len(confirmed_rows),
        "skipped_count": len(skipped),
        "confirmed": confirmed_rows,
        "skipped": skipped,
    }


@app.get("/reconciliation/workspace")
def reconciliation_workspace(
    limit: int = 30,
    branch: str | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    """Return batch cards + aggregate reconciliation counts in two DB queries.

    The previous UI called /uploads/recent and then one /reconciliation/{id}
    request for every visible batch. On serverless this amplified cold starts and
    made the page feel slow. This endpoint returns only the summary data needed
    for the initial screen; full row detail is fetched on demand.
    """
    safe_limit = min(max(limit, 1), 50)
    effective_branch = scoped_branch(user, branch)

    batch_stmt = (
        select(ImportBatch)
        .order_by(ImportBatch.uploaded_at.desc(), ImportBatch.id.desc())
        .limit(safe_limit)
    )
    if effective_branch is not None:
        batch_stmt = batch_stmt.where(ImportBatch.branch == effective_branch)
    batches = list(db.scalars(batch_stmt).all())
    if not batches:
        return {"items": []}

    batch_ids = [batch.id for batch in batches]
    rec_rows = db.execute(
        select(
            SAPBilling.import_batch_id,
            BillingReconciliation.status,
            BillingReconciliation.exception_code,
            BillingReconciliation.physical_billing_id,
            BillingReconciliation.remarks,
        )
        .join(
            BillingReconciliation,
            BillingReconciliation.sap_billing_id == SAPBilling.id,
        )
        .where(SAPBilling.import_batch_id.in_(batch_ids))
    ).all()

    summaries: dict[int, dict[str, dict[str, int] | int]] = {}
    for batch in batches:
        summaries[batch.id] = {
            "counts": {"MATCH": 0, "REVIEW": 0, "EXCEPTION": 0, "NOT_FOUND": 0},
            "evidence_counts": {
                "LENGKAP": 0,
                "BILLING_BELUM_LENGKAP": 0,
                "SPJ_BELUM_LENGKAP": 0,
                "SPJ_OCR_INFO": 0,
                "SPJ_OCR_REVIEW": 0,
                "SPJ_PERLU_REVIEW": 0,
            },
            "reconciled_total": 0,
        }

    for import_batch_id, status, exception_code, physical_billing_id, remarks in rec_rows:
        summary = summaries.get(import_batch_id)
        if summary is None:
            continue
        counts = summary["counts"]
        counts[status] = int(counts.get(status, 0)) + 1
        state = _reconciliation_evidence_state_values(
            status=status,
            exception_code=exception_code,
            physical_billing_id=physical_billing_id,
            remarks=remarks,
        )
        evidence_counts = summary["evidence_counts"]
        evidence_counts[state] = int(evidence_counts.get(state, 0)) + 1
        summary["reconciled_total"] = int(summary["reconciled_total"]) + 1

    return {
        "items": [
            {
                "id": batch.id,
                "kind": "SAP",
                "file_name": batch.file_name,
                "branch": batch.branch,
                "period": batch.period,
                "status": batch.status,
                "total_records": batch.total_records,
                "uploaded_at": batch.uploaded_at,
                **summaries[batch.id],
            }
            for batch in batches
        ]
    }


@app.get("/reconciliation/{batch_id}")
def reconciliation_dashboard(batch_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    _batch_for_user(db, batch_id, user)
    rows = db.scalars(select(BillingReconciliation).join(BillingReconciliation.sap_billing).where(
        BillingReconciliation.sap_billing.has(import_batch_id=batch_id))).all()
    counts = {status: sum(1 for row in rows if row.status == status) for status in ("MATCH", "REVIEW", "EXCEPTION", "NOT_FOUND")}
    return {"batch_id": batch_id, "total": len(rows), "counts": counts,
            "rows": [_reconciliation_row_payload(r) for r in rows]}


@app.post("/spj/vouch")
def run_spj_vouching(branch: str | None = None, db: Session = Depends(get_db),
                     user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR"))):
    effective_branch = scoped_branch(user, branch)
    rows = vouch_spj(db, branch=effective_branch)
    record_audit(db, entity_type="VOUCHING", entity_id=None, action="SPJ_VOUCHING_RUN",
                 actor=user.user_id, status_to="COMPLETED", metadata={"total": len(rows)},
                 branch=effective_branch)
    db.commit()
    return {"total": len(rows), "results": [{
        "id": r.id,
        "billing_id": r.billing_id,
        "spj_id": r.spj_id,
        "no_spj_billing": r.no_spj_billing,
        "no_spj_document": r.no_spj_document,
        "status": r.status,
        "rule_code": r.rule_code,
        "remarks": r.remarks,
        "evidence_state": (
            "SPJ_BELUM_LENGKAP"
            if r.rule_code in {"BILLING_WITHOUT_SPJ", "SPJ_NOT_FOUND"}
            else (
                "SPJ_OCR_REVIEW"
                if r.rule_code == "SPJ_NUMBER_UNREADABLE_PAIRED_EVIDENCE"
                else (
                    "SPJ_PERLU_REVIEW"
                    if r.rule_code in {"DUPLICATE_SPJ_NUMBER", "DUPLICATE_PAIRED_SPJ_EVIDENCE"}
                    else "LENGKAP"
                )
            )
        ),
    } for r in rows]}


@app.get("/results/{billing_id}")
def get_overall_result(billing_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    try: return overall_result(db, billing_id, branch=scoped_branch(user))
    except ValueError as exc: raise handle_error(exc) from exc


@app.get("/exceptions")
def exceptions(branch: str | None = None, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    branch = scoped_branch(user, branch)
    rec_query = (
        select(BillingReconciliation)
        .join(BillingReconciliation.sap_billing)
        .join(SAPBilling.import_batch)
        .where(BillingReconciliation.status.in_(["EXCEPTION", "REVIEW", "NOT_FOUND"]))
    )
    vouch_query = (
        select(VouchingResult)
        .join(VouchingResult.billing)
        .join(PhysicalBilling.document)
        .where(VouchingResult.status.in_(["EXCEPTION", "REVIEW"]))
    )
    control_query = (
        select(DocumentControlEvidence)
        .join(DocumentControlEvidence.document)
        .where(DocumentControlEvidence.review_required == True)  # noqa: E712
    )
    if branch is not None:
        rec_query = rec_query.where(ImportBatch.branch == branch)
        vouch_query = vouch_query.where(Document.branch == branch)
        control_query = control_query.where(Document.branch == branch)
    recs = db.scalars(rec_query).all()
    vouches = db.scalars(vouch_query).all()
    control_rows = db.scalars(control_query).all()
    return {"total": len(recs) + len(vouches) + len(control_rows), "reconciliation": [{"id": r.id, "status": r.status, "code": r.exception_code,
        "remarks": r.remarks, "sap_billing_id": r.sap_billing_id} for r in recs],
        "vouching": [{"id": r.id, "status": r.status, "code": r.rule_code, "remarks": r.remarks,
        "billing_id": r.billing_id, "reviewer_id": r.reviewer_id} for r in vouches],
        "control_evidence": [{"id": row.id, "document_id": row.document_id, "review_required": row.review_required,
        "review_status": row.review_status, "reviewer_id": row.reviewer_id, "reviewer_remarks": row.reviewer_remarks,
        "review_reasons": [reason.strip() for reason in (row.review_reasons or "").split(";") if reason.strip()]} for row in control_rows]}


@app.get("/dashboard/control-evidence/export")
def export_control_evidence_dashboard(review_only: bool = False, limit: int = 500, branch: str | None = None,
                                      db: Session = Depends(get_db),
                                      user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    from app.services.reports import build_control_evidence_report

    path = build_control_evidence_report(db, review_only=review_only, limit=limit, branch=scoped_branch(user, branch))
    media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(path, filename=path.name, media_type=media)


@app.get("/dashboard/control-evidence")
def control_evidence_dashboard(review_only: bool = False, limit: int = 200, branch: str | None = None,
                               db: Session = Depends(get_db),
                               user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    return build_control_evidence_dashboard(db, review_only=review_only, limit=limit, branch=scoped_branch(user, branch))


@app.post("/reviews/control-evidence/{evidence_id}")
def review_control_evidence_result(evidence_id: int, status: str, remarks: str | None = None,
                                   db: Session = Depends(get_db),
                                   user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER"))):
    try:
        result = review_control_evidence(
            db, evidence_id, status=status, reviewer_id=user.user_id, remarks=remarks,
            branch=scoped_branch(user),
        )
        reviewed_document = db.get(Document, result.get("document_id")) if result.get("document_id") else None
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
            branch=reviewed_document.branch if reviewed_document else scoped_branch(user),
        )
        db.commit()
        return result
    except ValueError as exc:
        db.rollback(); raise handle_error(exc) from exc


@app.post("/reviews/vouching/{result_id}")
def review_vouching(result_id: int, status: str, reason_code: str | None = None, remarks: str | None = None,
                    db: Session = Depends(get_db),
                    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER"))):
    try:
        payload = review_vouching_result(
            db,
            result_id,
            status=status,
            reason_code=reason_code,
            remarks=remarks,
            reviewer_id=user.user_id,
            branch=scoped_branch(user),
        )
        result = db.get(VouchingResult, result_id)
        result_branch = result.billing.document.branch if result else scoped_branch(user)
        record_audit(
            db,
            entity_type="VOUCHING_RESULT",
            entity_id=result_id,
            action="MANUAL_REVIEW",
            actor=user.user_id,
            status_from=payload.get("previous_status"),
            status_to=payload.get("status"),
            remarks=remarks,
            metadata={
                "reason_code": payload.get("reviewer_decision", {}).get("reason_code"),
                "automated_status": payload.get("automated_result", {}).get("status"),
                "control_evidence_id": payload.get("control_evidence_id"),
                "linked_customer": payload.get("linked_customer"),
            },
            branch=result_branch,
        )
        db.commit()
        return payload
    except ValueError as exc:
        db.rollback()
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise handle_error(exc) from exc


@app.get("/documents/{document_id}")
def document_evidence(document_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    doc = _document_for_user(db, document_id, user)
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
    doc = _document_for_user(db, document_id, user)
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
                limit: int = 100, branch: str | None = None, db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    rows = list_audit_trail(db, entity_type=entity_type, entity_id=entity_id, limit=limit, branch=scoped_branch(user, branch))
    return {"total": len(rows), "entries": [{
        "id": row.id, "entity_type": row.entity_type, "entity_id": row.entity_id,
        "action": row.action, "status_from": row.status_from, "status_to": row.status_to,
        "actor": row.actor, "branch": row.branch, "remarks": row.remarks, "metadata": row.metadata_json,
        "created_at": row.created_at,
    } for row in rows]}


def _working_paper_storage_path(batch_id: int, token: str) -> str:
    return f"reports/working-paper/batch_{batch_id}_{token}.xlsx"


def _prepare_working_paper_bytes(
    db: Session,
    batch_id: int,
    *,
    branch: str | None,
) -> tuple[bytes, str]:
    from app.services.reports import build_working_paper_report, working_paper_cache_token

    token = working_paper_cache_token(db, batch_id, branch=branch)
    storage_path = _working_paper_storage_path(batch_id, token)

    if settings.use_supabase_storage:
        try:
            return download_bytes(storage_path), token
        except ValueError:
            pass

    path = build_working_paper_report(db, batch_id, branch=branch)
    content = path.read_bytes()
    if settings.use_supabase_storage:
        try:
            upload_bytes(
                storage_path,
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except ValueError:
            pass
    return content, token


@app.post("/reports/{batch_id}/working-paper/prepare")
def prepare_working_paper_report(
    batch_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    branch = scoped_branch(user)
    try:
        content, token = _prepare_working_paper_bytes(db, batch_id, branch=branch)
    except ValueError as exc:
        raise handle_error(exc) from exc
    return {"batch_id": batch_id, "ready": True, "bytes": len(content), "token": token}


@app.get("/reports/{batch_id}/working-paper")
def generate_working_paper_report(
    batch_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    branch = scoped_branch(user)
    try:
        content, token = _prepare_working_paper_bytes(db, batch_id, branch=branch)
    except ValueError as exc:
        raise handle_error(exc) from exc
    media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    filename = f"kertas_kerja_batch_{batch_id}_{token}.xlsx"
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/reports/{batch_id}")
def generate_report(batch_id: int, format: str = "xlsx", db: Session = Depends(get_db), user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER"))):
    from app.services.reports import build_report

    try:
        path = build_report(db, batch_id, format, branch=scoped_branch(user))
    except ValueError as exc:
        raise handle_error(exc) from exc
    media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if path.suffix == ".xlsx" else "application/pdf"
    return FileResponse(path, filename=path.name, media_type=media)
