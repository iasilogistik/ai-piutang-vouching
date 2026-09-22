from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.auth import CurrentUser, require_roles
from app.branch_access import ensure_branch_access, normalize_branch, scoped_branch
from app.database import SessionLocal
from app.models import (
    AuditClosing,
    AuditException,
    AuditReport,
    AuditWorkflowCase,
    BillingReconciliation,
    DocumentControlEvidence,
    ReviewWorkflow,
    SAPBilling,
    VouchingResult,
)


router = APIRouter()
_REGISTERED = False

TRANSITIONS = {
    "VOUCHING": {"CONTROL_EVIDENCE"},
    "CONTROL_EVIDENCE": {"EXCEPTION", "REVIEW"},
    "EXCEPTION": {"REVIEW"},
    "REVIEW": {"REPORT"},
    "REPORT": {"CLOSING"},
    "CLOSING": {"CLOSED"},
    "CLOSED": set(),
}

AUDITOR_TARGETS = {"CONTROL_EVIDENCE", "EXCEPTION", "REVIEW", "REPORT", "CLOSING"}
REVIEWER_TARGETS = {"CLOSED"}


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _require_transition_role(user: CurrentUser, target_stage: str) -> None:
    if user.role == "ADMIN":
        return
    if target_stage in AUDITOR_TARGETS and user.role != "AUDITOR":
        raise HTTPException(status_code=403, detail="AUDITOR role required for this workflow transition")
    if target_stage in REVIEWER_TARGETS and user.role != "REVIEWER":
        raise HTTPException(status_code=403, detail="REVIEWER role required for final workflow closure")


def _vouching_branch(row: VouchingResult) -> str:
    branch = normalize_branch(row.billing.document.branch if row.billing and row.billing.document else None)
    if branch is None:
        raise HTTPException(status_code=400, detail="Vouching result has no branch ownership")
    return branch


def _derive_control_evidence(db: Session, vouching: VouchingResult) -> DocumentControlEvidence | None:
    if vouching.control_evidence_id:
        return db.get(DocumentControlEvidence, vouching.control_evidence_id)
    if vouching.spj is None:
        return None
    return db.scalar(
        select(DocumentControlEvidence).where(
            DocumentControlEvidence.document_id == vouching.spj.document_id
        )
    )


def _reconciliation_trace(db: Session, vouching: VouchingResult) -> dict[str, int | None]:
    rec = db.scalar(
        select(BillingReconciliation)
        .where(BillingReconciliation.physical_billing_id == vouching.billing_id)
        .order_by(BillingReconciliation.id.desc())
    )
    sap = db.get(SAPBilling, rec.sap_billing_id) if rec else None
    return {
        "billing_document_id": vouching.billing.document_id if vouching.billing else None,
        "spj_document_id": vouching.spj.document_id if vouching.spj else None,
        "reconciliation_id": rec.id if rec else None,
        "sap_billing_id": sap.id if sap else None,
        "import_batch_id": sap.import_batch_id if sap else None,
    }


def _exception_condition(db: Session, row: AuditWorkflowCase) -> bool:
    vouching = db.get(VouchingResult, row.vouching_result_id)
    if vouching is None:
        raise HTTPException(status_code=409, detail="Linked vouching result no longer exists")
    evidence = db.get(DocumentControlEvidence, row.control_evidence_id) if row.control_evidence_id else None
    return (
        vouching.status in {"REVIEW", "EXCEPTION"}
        or evidence is None
        or bool(evidence.review_required)
        or (evidence.review_status in {"REVIEW", "EXCEPTION"} if evidence.review_status else False)
    )


def _validate_exception_link(db: Session, row: AuditWorkflowCase, exception_id: int | None) -> AuditException:
    target_id = exception_id or row.audit_exception_id
    if target_id is None:
        raise HTTPException(status_code=409, detail="audit_exception_id is required for EXCEPTION stage")
    exception = db.get(AuditException, target_id)
    if exception is None:
        raise HTTPException(status_code=404, detail="Audit exception not found")
    if normalize_branch(exception.branch) != normalize_branch(row.branch):
        raise HTTPException(status_code=404, detail="Audit exception not found")
    return exception


def _validate_review_link(db: Session, row: AuditWorkflowCase, workflow_id: int | None) -> ReviewWorkflow:
    target_id = workflow_id or row.review_workflow_id
    if target_id is None:
        raise HTTPException(status_code=409, detail="review_workflow_id is required for REVIEW stage")
    workflow = db.get(ReviewWorkflow, target_id)
    if workflow is None or normalize_branch(workflow.branch) != normalize_branch(row.branch):
        raise HTTPException(status_code=404, detail="Review workflow not found")

    eligible = {("VOUCHING_RESULT", row.vouching_result_id)}
    if row.control_evidence_id:
        eligible.add(("DOCUMENT_CONTROL_EVIDENCE", row.control_evidence_id))
    if row.audit_exception_id:
        eligible.add(("AUDIT_EXCEPTION", row.audit_exception_id))
    if (workflow.entity_type, workflow.entity_id) not in eligible:
        raise HTTPException(status_code=409, detail="Review workflow is not linked to a resource in this workflow case")
    return workflow


def _validate_report_link(db: Session, row: AuditWorkflowCase, report_id: int | None) -> AuditReport:
    target_id = report_id or row.audit_report_id
    if target_id is None:
        raise HTTPException(status_code=409, detail="audit_report_id is required for REPORT stage")
    report = db.get(AuditReport, target_id)
    if report is None or normalize_branch(report.branch) != normalize_branch(row.branch):
        raise HTTPException(status_code=404, detail="Audit report not found")
    return report


def _validate_closing_link(db: Session, row: AuditWorkflowCase, closing_id: int | None) -> AuditClosing:
    target_id = closing_id or row.audit_closing_id
    if target_id is None:
        raise HTTPException(status_code=409, detail="audit_closing_id is required for CLOSING stage")
    closing = db.get(AuditClosing, target_id)
    if closing is None or normalize_branch(closing.branch) != normalize_branch(row.branch):
        raise HTTPException(status_code=404, detail="Audit closing not found")
    if row.audit_report_id is None or closing.audit_report_id != row.audit_report_id:
        raise HTTPException(status_code=409, detail="Audit closing is not linked to this workflow case report")
    return closing


def create_workflow_case(
    db: Session,
    *,
    vouching_result_id: int,
    user: CurrentUser,
) -> AuditWorkflowCase:
    vouching = db.get(VouchingResult, vouching_result_id)
    if vouching is None:
        raise HTTPException(status_code=404, detail="Vouching result not found")
    branch = _vouching_branch(vouching)
    ensure_branch_access(user, branch)

    existing = db.scalar(
        select(AuditWorkflowCase).where(AuditWorkflowCase.vouching_result_id == vouching_result_id)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Workflow case already exists for vouching result")

    evidence = _derive_control_evidence(db, vouching)
    row = AuditWorkflowCase(
        branch=branch,
        vouching_result_id=vouching.id,
        control_evidence_id=evidence.id if evidence else None,
        stage="VOUCHING",
        created_by=user.user_id,
        updated_by=user.user_id,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        entity_type="AUDIT_WORKFLOW_CASE",
        entity_id=row.id,
        action="CREATE",
        actor=user.user_id,
        status_to=row.stage,
        branch=row.branch,
        metadata={
            "vouching_result_id": row.vouching_result_id,
            "control_evidence_id": row.control_evidence_id,
        },
    )
    db.flush()
    return row


def transition_workflow_case(
    db: Session,
    row: AuditWorkflowCase,
    *,
    target_stage: str,
    user: CurrentUser,
    audit_exception_id: int | None = None,
    review_workflow_id: int | None = None,
    audit_report_id: int | None = None,
    audit_closing_id: int | None = None,
) -> AuditWorkflowCase:
    target_stage = target_stage.strip().upper()
    if target_stage not in TRANSITIONS.get(row.stage, set()):
        raise HTTPException(status_code=400, detail=f"Invalid workflow transition: {row.stage} -> {target_stage}")
    ensure_branch_access(user, row.branch)
    _require_transition_role(user, target_stage)

    vouching = db.get(VouchingResult, row.vouching_result_id)
    if vouching is None:
        raise HTTPException(status_code=409, detail="Linked vouching result no longer exists")

    if target_stage == "CONTROL_EVIDENCE":
        evidence = _derive_control_evidence(db, vouching)
        row.control_evidence_id = evidence.id if evidence else None

    elif target_stage == "EXCEPTION":
        if not _exception_condition(db, row):
            raise HTTPException(status_code=409, detail="No exception condition is present; proceed to REVIEW")
        exception = _validate_exception_link(db, row, audit_exception_id)
        row.audit_exception_id = exception.id

    elif target_stage == "REVIEW":
        if row.stage == "CONTROL_EVIDENCE" and _exception_condition(db, row):
            raise HTTPException(status_code=409, detail="Exception condition must be linked before REVIEW")
        if row.stage == "EXCEPTION":
            _validate_exception_link(db, row, row.audit_exception_id)
        workflow = _validate_review_link(db, row, review_workflow_id)
        row.review_workflow_id = workflow.id

    elif target_stage == "REPORT":
        workflow = _validate_review_link(db, row, row.review_workflow_id)
        if workflow.status != "CLOSED":
            raise HTTPException(status_code=409, detail="Review workflow must be CLOSED before REPORT")
        report = _validate_report_link(db, row, audit_report_id)
        row.audit_report_id = report.id

    elif target_stage == "CLOSING":
        report = _validate_report_link(db, row, row.audit_report_id)
        if report.status != "APPROVED":
            raise HTTPException(status_code=409, detail="Audit report must be APPROVED before CLOSING")
        closing = _validate_closing_link(db, row, audit_closing_id)
        row.audit_closing_id = closing.id

    elif target_stage == "CLOSED":
        closing = _validate_closing_link(db, row, row.audit_closing_id)
        if closing.status != "CLOSED":
            raise HTTPException(status_code=409, detail="Audit closing must be CLOSED before workflow closure")

    previous_stage = row.stage
    row.stage = target_stage
    row.updated_by = user.user_id
    record_audit(
        db,
        entity_type="AUDIT_WORKFLOW_CASE",
        entity_id=row.id,
        action="TRANSITION",
        actor=user.user_id,
        status_from=previous_stage,
        status_to=target_stage,
        branch=row.branch,
        metadata={
            "vouching_result_id": row.vouching_result_id,
            "control_evidence_id": row.control_evidence_id,
            "audit_exception_id": row.audit_exception_id,
            "review_workflow_id": row.review_workflow_id,
            "audit_report_id": row.audit_report_id,
            "audit_closing_id": row.audit_closing_id,
        },
    )
    db.flush()
    return row


def workflow_case_payload(db: Session, row: AuditWorkflowCase) -> dict[str, object]:
    vouching = db.get(VouchingResult, row.vouching_result_id)
    trace = _reconciliation_trace(db, vouching) if vouching else {
        "billing_document_id": None,
        "spj_document_id": None,
        "reconciliation_id": None,
        "sap_billing_id": None,
        "import_batch_id": None,
    }
    evidence = db.get(DocumentControlEvidence, row.control_evidence_id) if row.control_evidence_id else None
    exception = db.get(AuditException, row.audit_exception_id) if row.audit_exception_id else None
    review = db.get(ReviewWorkflow, row.review_workflow_id) if row.review_workflow_id else None
    report = db.get(AuditReport, row.audit_report_id) if row.audit_report_id else None
    closing = db.get(AuditClosing, row.audit_closing_id) if row.audit_closing_id else None

    return {
        "id": row.id,
        "branch": row.branch,
        "stage": row.stage,
        "allowed_transitions": sorted(TRANSITIONS.get(row.stage, set())),
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "resources": {
            **trace,
            "vouching_result_id": row.vouching_result_id,
            "vouching_status": vouching.status if vouching else None,
            "control_evidence_id": row.control_evidence_id,
            "control_evidence_status": (
                evidence.review_status or ("REVIEW" if evidence.review_required else "PASS")
                if evidence else "NOT_FOUND"
            ),
            "audit_exception_id": row.audit_exception_id,
            "audit_exception_status": exception.status if exception else None,
            "review_workflow_id": row.review_workflow_id,
            "review_workflow_status": review.status if review else None,
            "audit_report_id": row.audit_report_id,
            "audit_report_status": report.status if report else None,
            "audit_closing_id": row.audit_closing_id,
            "audit_closing_status": closing.status if closing else None,
        },
    }


def list_workflow_cases(db: Session, *, branch: str | None = None, stage: str | None = None) -> list[AuditWorkflowCase]:
    query = select(AuditWorkflowCase).order_by(AuditWorkflowCase.updated_at.desc(), AuditWorkflowCase.id.desc())
    if branch is not None:
        query = query.where(AuditWorkflowCase.branch == normalize_branch(branch))
    if stage:
        stage = stage.strip().upper()
        if stage not in TRANSITIONS:
            raise HTTPException(status_code=400, detail="Invalid workflow stage")
        query = query.where(AuditWorkflowCase.stage == stage)
    return list(db.scalars(query).all())


def _html() -> str:
    return """<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit Workflow - AI Piutang Vouching</title>
<style>
body{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}header{background:#0f172a;color:white;padding:18px 24px}
main{max-width:1220px;margin:auto;padding:20px}.panel{background:#fff;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}label{display:block;font-size:12px;color:#64748b;margin-bottom:4px}
input,select,button{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}button{background:#1f6feb;color:white;font-weight:700;cursor:pointer}
.flow{display:flex;gap:8px;flex-wrap:wrap}.step{background:#e2e8f0;padding:8px 10px;border-radius:999px;font-size:12px;font-weight:700}
table{width:100%;border-collapse:collapse}th,td{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px}
pre{white-space:pre-wrap;background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px}@media(max-width:850px){.grid{grid-template-columns:1fr 1fr}}
</style></head><body>
<header><h1>End-to-End Audit Workflow</h1><p>Trace Upload/Import → Vouching → Evidence → Exception → Review → Report → Closing.</p></header>
<main>
<section class="panel"><div class="flow"><span class="step">VOUCHING</span><span>→</span><span class="step">CONTROL_EVIDENCE</span><span>→</span><span class="step">EXCEPTION (bila perlu)</span><span>→</span><span class="step">REVIEW</span><span>→</span><span class="step">REPORT</span><span>→</span><span class="step">CLOSING</span><span>→</span><span class="step">CLOSED</span></div></section>
<section class="panel"><div class="grid">
<div><label>Bearer Token</label><input id="token" type="password"></div><div><label>Cabang</label><input id="branch" placeholder="ADMIN: kosong = semua"></div>
<div><label>Stage</label><select id="filterStage"><option value="">Semua</option><option>VOUCHING</option><option>CONTROL_EVIDENCE</option><option>EXCEPTION</option><option>REVIEW</option><option>REPORT</option><option>CLOSING</option><option>CLOSED</option></select></div>
<div><button id="load" style="margin-top:18px">Muat Workflow</button></div></div></section>
<section class="panel"><h2>Buat Workflow Case</h2><div class="grid"><div><label>Vouching Result ID</label><input id="vouchId" type="number" min="1"></div><div><button id="create" style="margin-top:18px">Buat Case</button></div></div></section>
<section class="panel"><h2>Transition & Link Resource</h2><div class="grid">
<div><label>Case ID</label><input id="caseId" type="number" min="1"></div>
<div><label>Target Stage</label><select id="target"><option>CONTROL_EVIDENCE</option><option>EXCEPTION</option><option>REVIEW</option><option>REPORT</option><option>CLOSING</option><option>CLOSED</option></select></div>
<div><label>Exception ID</label><input id="exceptionId" type="number"></div><div><label>Review Workflow ID</label><input id="reviewId" type="number"></div>
<div><label>Audit Report ID</label><input id="reportId" type="number"></div><div><label>Audit Closing ID</label><input id="closingId" type="number"></div>
<div><button id="transition" style="margin-top:18px">Proses Transition</button></div></div></section>
<section class="panel"><table><thead><tr><th>ID</th><th>Cabang</th><th>Stage</th><th>Vouching</th><th>Evidence</th><th>Exception</th><th>Review</th><th>Report</th><th>Closing</th><th>Next</th></tr></thead><tbody id="rows"><tr><td colspan="10">Belum dimuat.</td></tr></tbody></table></section>
<section class="panel"><pre id="log">Belum ada aktivitas.</pre></section>
</main><script>
const t=document.getElementById('token');t.value=localStorage.getItem('auditToken')||'';
function headers(){const x=t.value.trim();if(!x)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',x);return {Authorization:'Bearer '+x}}
async function load(){const p=new URLSearchParams();const b=document.getElementById('branch').value.trim();const s=document.getElementById('filterStage').value;if(b)p.set('branch',b);if(s)p.set('stage',s);const r=await fetch('/audit-workflow-cases?'+p.toString(),{headers:headers()});const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));const rows=x.cases||[];document.getElementById('rows').innerHTML=rows.length?rows.map(v=>{const q=v.resources;return '<tr><td>'+v.id+'</td><td>'+v.branch+'</td><td>'+v.stage+'</td><td>'+q.vouching_result_id+'</td><td>'+(q.control_evidence_id||'-')+'</td><td>'+(q.audit_exception_id||'-')+'</td><td>'+(q.review_workflow_id||'-')+'</td><td>'+(q.audit_report_id||'-')+'</td><td>'+(q.audit_closing_id||'-')+'</td><td>'+v.allowed_transitions.join(', ')+'</td></tr>'}).join(''):'<tr><td colspan="10">Tidak ada workflow.</td></tr>';document.getElementById('log').textContent=JSON.stringify(x,null,2)}
async function createCase(){const fd=new FormData();fd.append('vouching_result_id',document.getElementById('vouchId').value);const r=await fetch('/audit-workflow-cases',{method:'POST',headers:headers(),body:fd});const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));document.getElementById('log').textContent=JSON.stringify(x,null,2);await load()}
async function transition(){const id=document.getElementById('caseId').value;const fd=new FormData();fd.append('stage',document.getElementById('target').value);for(const [el,key] of [['exceptionId','audit_exception_id'],['reviewId','review_workflow_id'],['reportId','audit_report_id'],['closingId','audit_closing_id']]){const v=document.getElementById(el).value;if(v)fd.append(key,v)}const r=await fetch('/audit-workflow-cases/'+encodeURIComponent(id)+'/transition',{method:'POST',headers:headers(),body:fd});const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));document.getElementById('log').textContent=JSON.stringify(x,null,2);await load()}
document.getElementById('load').onclick=()=>load().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
document.getElementById('create').onclick=()=>createCase().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
document.getElementById('transition').onclick=()=>transition().catch(e=>document.getElementById('log').textContent='ERROR: '+e.message);
</script></body></html>"""


@router.get("/ui/audit-workflow", response_class=HTMLResponse)
def audit_workflow_ui():
    return HTMLResponse(_html())


@router.get("/audit-workflow-cases")
def get_workflow_cases(
    branch: str | None = None,
    stage: str | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    rows = list_workflow_cases(db, branch=effective_branch, stage=stage)
    return {
        "total": len(rows),
        "branch": effective_branch,
        "cases": [workflow_case_payload(db, row) for row in rows],
    }


@router.get("/audit-workflow-cases/{case_id}")
def get_workflow_case(
    case_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    row = db.get(AuditWorkflowCase, case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow case not found")
    ensure_branch_access(user, row.branch)
    return workflow_case_payload(db, row)


@router.post("/audit-workflow-cases")
def create_case(
    vouching_result_id: int = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = create_workflow_case(db, vouching_result_id=vouching_result_id, user=user)
    db.commit()
    db.refresh(row)
    return workflow_case_payload(db, row)


@router.post("/audit-workflow-cases/{case_id}/transition")
def transition_case(
    case_id: int,
    stage: str = Form(...),
    audit_exception_id: int | None = Form(None),
    review_workflow_id: int | None = Form(None),
    audit_report_id: int | None = Form(None),
    audit_closing_id: int | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER")),
):
    row = db.get(AuditWorkflowCase, case_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Workflow case not found")
    transition_workflow_case(
        db,
        row,
        target_stage=stage,
        user=user,
        audit_exception_id=audit_exception_id,
        review_workflow_id=review_workflow_id,
        audit_report_id=audit_report_id,
        audit_closing_id=audit_closing_id,
    )
    db.commit()
    db.refresh(row)
    return workflow_case_payload(db, row)


def register_audit_workflow_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
