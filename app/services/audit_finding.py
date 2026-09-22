from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.auth import CurrentUser, require_roles
from app.branch_access import ensure_branch_access, normalize_branch, scoped_branch
from app.database import SessionLocal
from app.models import (
    AuditEngagement,
    AuditEngagementAssignment,
    AuditException,
    AuditFinding,
    AuditFindingEvidence,
    AuditFindingException,
    AuditFindingSample,
    AuditFindingVersion,
    AuditFindingWorkingPaper,
    AuditSample,
    AuditWorkingPaper,
    Document,
    DocumentControlEvidence,
)

router = APIRouter()
_REGISTERED = False

TRANSITIONS = {
    "DRAFT": {"IN_REVIEW"},
    "IN_REVIEW": {"APPROVED"},
    "APPROVED": {"ISSUED"},
    "ISSUED": set(),
}
SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _is_assigned(db: Session, engagement_id: int, user: CurrentUser, assignment_role: str) -> bool:
    if user.role == "ADMIN":
        return True
    if user.role != assignment_role:
        return False
    return db.scalar(
        select(AuditEngagementAssignment.id).where(
            AuditEngagementAssignment.engagement_id == engagement_id,
            AuditEngagementAssignment.user_id == user.user_id,
            AuditEngagementAssignment.assignment_role == assignment_role,
        )
    ) is not None


def _require_assignment(db: Session, engagement_id: int, user: CurrentUser, role: str) -> None:
    if not _is_assigned(db, engagement_id, user, role):
        raise HTTPException(status_code=403, detail=f"Assigned {role} role required")


def _require_draft(row: AuditFinding) -> None:
    if row.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only DRAFT findings can be modified")


def _snapshot(
    db: Session,
    row: AuditFinding,
    *,
    user: CurrentUser,
    status: str,
    reason: str | None = None,
    increment: bool = True,
) -> AuditFindingVersion:
    if increment:
        row.version_number += 1
    version = AuditFindingVersion(
        finding_id=row.id,
        version_number=row.version_number,
        title=row.title,
        condition=row.condition,
        criteria=row.criteria,
        cause=row.cause,
        effect_risk=row.effect_risk,
        recommendation=row.recommendation,
        severity=row.severity,
        status=status,
        changed_by=user.user_id,
        change_reason=reason,
    )
    db.add(version)
    db.flush()
    return version


def _complete(row: AuditFinding) -> bool:
    return all(
        value and value.strip()
        for value in (
            row.title,
            row.condition,
            row.criteria,
            row.cause,
            row.effect_risk,
            row.recommendation,
        )
    )


def finding_payload(db: Session, row: AuditFinding) -> dict[str, object]:
    versions = list(
        db.scalars(
            select(AuditFindingVersion)
            .where(AuditFindingVersion.finding_id == row.id)
            .order_by(AuditFindingVersion.version_number)
        ).all()
    )
    working_papers = list(
        db.scalars(
            select(AuditFindingWorkingPaper)
            .where(AuditFindingWorkingPaper.finding_id == row.id)
            .order_by(AuditFindingWorkingPaper.id)
        ).all()
    )
    evidence = list(
        db.scalars(
            select(AuditFindingEvidence)
            .where(AuditFindingEvidence.finding_id == row.id)
            .order_by(AuditFindingEvidence.id)
        ).all()
    )
    exceptions = list(
        db.scalars(
            select(AuditFindingException)
            .where(AuditFindingException.finding_id == row.id)
            .order_by(AuditFindingException.id)
        ).all()
    )
    samples = list(
        db.scalars(
            select(AuditFindingSample)
            .where(AuditFindingSample.finding_id == row.id)
            .order_by(AuditFindingSample.id)
        ).all()
    )
    return {
        "id": row.id,
        "engagement_id": row.engagement_id,
        "branch": row.branch,
        "reference": row.reference,
        "title": row.title,
        "condition": row.condition,
        "criteria": row.criteria,
        "cause": row.cause,
        "effect_risk": row.effect_risk,
        "recommendation": row.recommendation,
        "severity": row.severity,
        "status": row.status,
        "version_number": row.version_number,
        "preparer_id": row.preparer_id,
        "reviewer_id": row.reviewer_id,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "issued_at": row.issued_at.isoformat() if row.issued_at else None,
        "allowed_transitions": sorted(TRANSITIONS.get(row.status, set())),
        "working_paper_ids": [x.working_paper_id for x in working_papers],
        "evidence": [
            {
                "id": x.id,
                "document_id": x.document_id,
                "control_evidence_id": x.control_evidence_id,
            }
            for x in evidence
        ],
        "exception_ids": [x.audit_exception_id for x in exceptions],
        "sample_ids": [x.sample_id for x in samples],
        "versions": [
            {
                "version_number": x.version_number,
                "status": x.status,
                "changed_by": x.changed_by,
                "change_reason": x.change_reason,
                "created_at": x.created_at.isoformat() if x.created_at else None,
            }
            for x in versions
        ],
    }


def create_finding(
    db: Session,
    *,
    engagement: AuditEngagement,
    reference: str,
    title: str,
    severity: str,
    user: CurrentUser,
) -> AuditFinding:
    ensure_branch_access(user, engagement.branch)
    _require_assignment(db, engagement.id, user, "AUDITOR")
    if engagement.status == "CLOSED":
        raise HTTPException(status_code=409, detail="Closed engagement cannot receive findings")

    clean_reference = reference.strip().upper()
    clean_title = title.strip()
    clean_severity = severity.strip().upper()
    if not clean_reference or not clean_title:
        raise HTTPException(status_code=400, detail="reference and title are required")
    if clean_severity not in SEVERITIES:
        raise HTTPException(status_code=400, detail="Invalid finding severity")
    if db.scalar(
        select(AuditFinding.id).where(
            AuditFinding.engagement_id == engagement.id,
            AuditFinding.reference == clean_reference,
        )
    ) is not None:
        raise HTTPException(status_code=409, detail="Finding reference already exists in this engagement")

    row = AuditFinding(
        engagement_id=engagement.id,
        branch=engagement.branch,
        reference=clean_reference,
        title=clean_title,
        severity=clean_severity,
        status="DRAFT",
        version_number=1,
        preparer_id=user.user_id,
    )
    db.add(row)
    db.flush()
    _snapshot(db, row, user=user, status="DRAFT", increment=False)
    record_audit(
        db,
        entity_type="AUDIT_FINDING",
        entity_id=row.id,
        action="CREATE",
        actor=user.user_id,
        status_to="DRAFT",
        branch=row.branch,
        metadata={"engagement_id": row.engagement_id, "reference": row.reference, "severity": row.severity},
    )
    db.flush()
    return row


def update_finding(
    db: Session,
    row: AuditFinding,
    *,
    title: str | None,
    condition: str | None,
    criteria: str | None,
    cause: str | None,
    effect_risk: str | None,
    recommendation: str | None,
    severity: str | None,
    user: CurrentUser,
) -> AuditFinding:
    ensure_branch_access(user, row.branch)
    _require_assignment(db, row.engagement_id, user, "AUDITOR")
    _require_draft(row)

    updates = {
        "title": title,
        "condition": condition,
        "criteria": criteria,
        "cause": cause,
        "effect_risk": effect_risk,
        "recommendation": recommendation,
    }
    changed: list[str] = []
    for field, value in updates.items():
        if value is None:
            continue
        clean = value.strip()
        if field == "title" and not clean:
            raise HTTPException(status_code=400, detail="title cannot be blank")
        new_value = clean or None
        if getattr(row, field) != new_value:
            setattr(row, field, new_value)
            changed.append(field)

    if severity is not None:
        clean_severity = severity.strip().upper()
        if clean_severity not in SEVERITIES:
            raise HTTPException(status_code=400, detail="Invalid finding severity")
        if row.severity != clean_severity:
            row.severity = clean_severity
            changed.append("severity")

    if changed:
        record_audit(
            db,
            entity_type="AUDIT_FINDING",
            entity_id=row.id,
            action="UPDATE",
            actor=user.user_id,
            branch=row.branch,
            metadata={"fields": sorted(changed)},
        )
    db.flush()
    return row


def transition_finding(
    db: Session,
    row: AuditFinding,
    *,
    target_status: str,
    user: CurrentUser,
) -> AuditFinding:
    ensure_branch_access(user, row.branch)
    target = target_status.strip().upper()
    if target not in TRANSITIONS.get(row.status, set()):
        raise HTTPException(status_code=400, detail=f"Invalid finding transition: {row.status} -> {target}")

    if target == "IN_REVIEW":
        _require_assignment(db, row.engagement_id, user, "AUDITOR")
        if not _complete(row):
            raise HTTPException(status_code=400, detail="5C fields and recommendation are required before review")
    else:
        _require_assignment(db, row.engagement_id, user, "REVIEWER")
        if not _complete(row):
            raise HTTPException(status_code=400, detail="Finding is incomplete")

    previous = row.status
    row.status = target
    now = datetime.now(timezone.utc)
    if target == "APPROVED":
        row.reviewer_id = user.user_id
        row.approved_at = now
        _snapshot(db, row, user=user, status=target)
    elif target == "ISSUED":
        row.reviewer_id = user.user_id
        row.issued_at = now
        _snapshot(db, row, user=user, status=target)

    record_audit(
        db,
        entity_type="AUDIT_FINDING",
        entity_id=row.id,
        action="TRANSITION",
        actor=user.user_id,
        status_from=previous,
        status_to=target,
        branch=row.branch,
        metadata={"version_number": row.version_number, "severity": row.severity},
    )
    db.flush()
    return row


def reopen_finding(
    db: Session,
    row: AuditFinding,
    *,
    reason: str,
    user: CurrentUser,
) -> AuditFinding:
    ensure_branch_access(user, row.branch)
    _require_assignment(db, row.engagement_id, user, "REVIEWER")
    if row.status not in {"APPROVED", "ISSUED"}:
        raise HTTPException(status_code=400, detail="Only APPROVED or ISSUED findings can be reopened")
    clean_reason = reason.strip()
    if not clean_reason:
        raise HTTPException(status_code=400, detail="Reopen reason is required")

    previous = row.status
    row.status = "DRAFT"
    row.reviewer_id = None
    row.approved_at = None
    row.issued_at = None
    _snapshot(db, row, user=user, status="DRAFT", reason=clean_reason)
    record_audit(
        db,
        entity_type="AUDIT_FINDING",
        entity_id=row.id,
        action="REOPEN",
        actor=user.user_id,
        status_from=previous,
        status_to="DRAFT",
        remarks=clean_reason,
        branch=row.branch,
        metadata={"version_number": row.version_number},
    )
    db.flush()
    return row


def _link_guard(db: Session, row: AuditFinding, user: CurrentUser) -> None:
    ensure_branch_access(user, row.branch)
    _require_assignment(db, row.engagement_id, user, "AUDITOR")
    _require_draft(row)


def link_working_paper(
    db: Session, row: AuditFinding, *, working_paper_id: int, user: CurrentUser
) -> AuditFindingWorkingPaper:
    _link_guard(db, row, user)
    wp = db.get(AuditWorkingPaper, working_paper_id)
    if wp is None or wp.engagement_id != row.engagement_id or normalize_branch(wp.branch) != normalize_branch(row.branch):
        raise HTTPException(status_code=404, detail="Working paper not found")
    existing = db.scalar(
        select(AuditFindingWorkingPaper.id).where(
            AuditFindingWorkingPaper.finding_id == row.id,
            AuditFindingWorkingPaper.working_paper_id == wp.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Working paper already linked")
    link = AuditFindingWorkingPaper(finding_id=row.id, working_paper_id=wp.id, linked_by=user.user_id)
    db.add(link)
    db.flush()
    record_audit(db, entity_type="AUDIT_FINDING", entity_id=row.id, action="LINK_WORKING_PAPER", actor=user.user_id, branch=row.branch, metadata={"working_paper_id": wp.id})
    return link


def link_evidence(
    db: Session,
    row: AuditFinding,
    *,
    document_id: int | None,
    control_evidence_id: int | None,
    user: CurrentUser,
) -> AuditFindingEvidence:
    _link_guard(db, row, user)
    if (document_id is None) == (control_evidence_id is None):
        raise HTTPException(status_code=400, detail="Provide exactly one evidence source")
    document = db.get(Document, document_id) if document_id is not None else None
    if control_evidence_id is not None:
        control = db.get(DocumentControlEvidence, control_evidence_id)
        document = control.document if control else None
    if document is None or normalize_branch(document.branch) != normalize_branch(row.branch):
        raise HTTPException(status_code=404, detail="Evidence not found")
    existing = db.scalar(
        select(AuditFindingEvidence.id).where(
            AuditFindingEvidence.finding_id == row.id,
            AuditFindingEvidence.document_id == document_id,
            AuditFindingEvidence.control_evidence_id == control_evidence_id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Evidence already linked")
    link = AuditFindingEvidence(
        finding_id=row.id,
        document_id=document_id,
        control_evidence_id=control_evidence_id,
        linked_by=user.user_id,
    )
    db.add(link)
    db.flush()
    record_audit(db, entity_type="AUDIT_FINDING", entity_id=row.id, action="LINK_EVIDENCE", actor=user.user_id, branch=row.branch, metadata={"document_id": document_id, "control_evidence_id": control_evidence_id})
    return link


def link_exception(
    db: Session, row: AuditFinding, *, audit_exception_id: int, user: CurrentUser
) -> AuditFindingException:
    _link_guard(db, row, user)
    exception = db.get(AuditException, audit_exception_id)
    if exception is None or normalize_branch(exception.branch) != normalize_branch(row.branch):
        raise HTTPException(status_code=404, detail="Audit exception not found")
    existing = db.scalar(
        select(AuditFindingException.id).where(
            AuditFindingException.finding_id == row.id,
            AuditFindingException.audit_exception_id == exception.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Audit exception already linked")
    link = AuditFindingException(finding_id=row.id, audit_exception_id=exception.id, linked_by=user.user_id)
    db.add(link)
    db.flush()
    record_audit(db, entity_type="AUDIT_FINDING", entity_id=row.id, action="LINK_EXCEPTION", actor=user.user_id, branch=row.branch, metadata={"audit_exception_id": exception.id})
    return link


def link_sample(
    db: Session, row: AuditFinding, *, sample_id: int, user: CurrentUser
) -> AuditFindingSample:
    _link_guard(db, row, user)
    sample = db.get(AuditSample, sample_id)
    if sample is None or sample.engagement_id != row.engagement_id or normalize_branch(sample.branch) != normalize_branch(row.branch):
        raise HTTPException(status_code=404, detail="Audit sample not found")
    existing = db.scalar(
        select(AuditFindingSample.id).where(
            AuditFindingSample.finding_id == row.id,
            AuditFindingSample.sample_id == sample.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Audit sample already linked")
    link = AuditFindingSample(finding_id=row.id, sample_id=sample.id, linked_by=user.user_id)
    db.add(link)
    db.flush()
    record_audit(db, entity_type="AUDIT_FINDING", entity_id=row.id, action="LINK_SAMPLE", actor=user.user_id, branch=row.branch, metadata={"sample_id": sample.id})
    return link


def _unlink(db: Session, row: AuditFinding, link, *, action: str, metadata: dict, user: CurrentUser) -> None:
    _link_guard(db, row, user)
    if link is None or link.finding_id != row.id:
        raise HTTPException(status_code=404, detail="Finding link not found")
    db.delete(link)
    record_audit(db, entity_type="AUDIT_FINDING", entity_id=row.id, action=action, actor=user.user_id, branch=row.branch, metadata=metadata)
    db.flush()


def _finding_for_user(db: Session, finding_id: int, user: CurrentUser) -> AuditFinding:
    row = db.get(AuditFinding, finding_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit finding not found")
    ensure_branch_access(user, row.branch)
    return row


def _html() -> str:
    stages = " → ".join(TRANSITIONS)
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit Findings - AI Piutang Vouching</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}}header{{background:#0f172a;color:white;padding:18px 24px}}
main{{max-width:1200px;margin:auto;padding:20px}}.panel{{background:white;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}}
.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}input,select,textarea,button{{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}}
textarea{{min-height:70px}}button{{background:#1f6feb;color:white;font-weight:700;cursor:pointer}}table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px}}
pre{{white-space:pre-wrap;background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>Audit Finding Management</h1><p>{escape(stages)}; formal findings preserve 5C evidence and version history.</p></header><main>
<section class="panel"><div class="grid"><input id="token" type="password" placeholder="Bearer token"><input id="engagementFilter" type="number" placeholder="Engagement ID"><button id="load">Muat Findings</button></div></section>
<section class="panel"><h2>Buat Finding</h2><div class="grid"><input id="engagementId" type="number" placeholder="Engagement ID"><input id="reference" placeholder="Reference"><input id="title" placeholder="Title"><select id="severity"><option>LOW</option><option selected>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select><button id="create">Buat Draft</button></div></section>
<section class="panel"><h2>Update 5C</h2><div class="grid"><input id="findingId" type="number" placeholder="Finding ID"><textarea id="condition" placeholder="Condition"></textarea><textarea id="criteria" placeholder="Criteria"></textarea><textarea id="cause" placeholder="Cause"></textarea><textarea id="effect" placeholder="Effect / Risk"></textarea><textarea id="recommendation" placeholder="Recommendation"></textarea><button id="save">Simpan Draft</button><select id="target"><option>IN_REVIEW</option><option>APPROVED</option><option>ISSUED</option></select><button id="transition">Transition</button><input id="reopenReason" placeholder="Reopen reason"><button id="reopen">Reopen</button></div></section>
<section class="panel"><table><thead><tr><th>ID</th><th>Ref</th><th>Title</th><th>Branch</th><th>Severity</th><th>Status</th><th>Version</th></tr></thead><tbody id="rows"><tr><td colspan="7">Belum dimuat.</td></tr></tbody></table></section>
<section class="panel"><pre id="log">Belum ada aktivitas.</pre></section></main>
<script>
const token=document.getElementById('token');token.value=localStorage.getItem('auditToken')||'';const log=document.getElementById('log');const rows=document.getElementById('rows');
function headers(){{const v=token.value.trim();if(!v)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',v);return {{Authorization:'Bearer '+v}}}}
async function req(url,opt={{}}){{opt.headers=Object.assign({{}},opt.headers||{{}},headers());const r=await fetch(url,opt);const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));log.textContent=JSON.stringify(x,null,2);return x}}
async function loadData(){{const p=new URLSearchParams();const id=document.getElementById('engagementFilter').value;if(id)p.set('engagement_id',id);const x=await req('/audit-findings?'+p);rows.innerHTML=(x.findings||[]).map(f=>'<tr><td>'+f.id+'</td><td>'+f.reference+'</td><td>'+f.title+'</td><td>'+f.branch+'</td><td>'+f.severity+'</td><td>'+f.status+'</td><td>'+f.version_number+'</td></tr>').join('')||'<tr><td colspan="7">Tidak ada finding.</td></tr>'}}
async function post(url,data,method='POST'){{const fd=new FormData();Object.entries(data).forEach(([k,v])=>{{if(v!==''&&v!=null)fd.append(k,v)}});return req(url,{{method,body:fd}})}}
document.getElementById('load').onclick=()=>loadData().catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('create').onclick=()=>post('/audit-findings',{{engagement_id:document.getElementById('engagementId').value,reference:document.getElementById('reference').value,title:document.getElementById('title').value,severity:document.getElementById('severity').value}}).then(loadData).catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('save').onclick=()=>post('/audit-findings/'+document.getElementById('findingId').value,{{condition:document.getElementById('condition').value,criteria:document.getElementById('criteria').value,cause:document.getElementById('cause').value,effect_risk:document.getElementById('effect').value,recommendation:document.getElementById('recommendation').value}},'PATCH').then(loadData).catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('transition').onclick=()=>post('/audit-findings/'+document.getElementById('findingId').value+'/transition',{{status:document.getElementById('target').value}}).then(loadData).catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('reopen').onclick=()=>post('/audit-findings/'+document.getElementById('findingId').value+'/reopen',{{reason:document.getElementById('reopenReason').value}}).then(loadData).catch(e=>log.textContent='ERROR: '+e.message);
</script></body></html>"""


@router.get("/ui/audit-findings", response_class=HTMLResponse)
def audit_findings_ui():
    return HTMLResponse(_html())


@router.get("/audit-findings")
def get_findings(
    engagement_id: int | None = None,
    branch: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    query = select(AuditFinding).order_by(AuditFinding.updated_at.desc(), AuditFinding.id.desc())
    if effective_branch is not None:
        query = query.where(AuditFinding.branch == effective_branch)
    if engagement_id is not None:
        query = query.where(AuditFinding.engagement_id == engagement_id)
    if status:
        query = query.where(AuditFinding.status == status.strip().upper())
    if severity:
        query = query.where(AuditFinding.severity == severity.strip().upper())
    rows = list(db.scalars(query).all())
    return {"total": len(rows), "findings": [finding_payload(db, row) for row in rows]}


@router.get("/audit-findings/{finding_id}")
def get_finding(
    finding_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    return finding_payload(db, _finding_for_user(db, finding_id, user))


@router.post("/audit-findings")
def post_finding(
    engagement_id: int = Form(...),
    reference: str = Form(...),
    title: str = Form(...),
    severity: str = Form("MEDIUM"),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    engagement = db.get(AuditEngagement, engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="Audit engagement not found")
    row = create_finding(db, engagement=engagement, reference=reference, title=title, severity=severity, user=user)
    db.commit()
    db.refresh(row)
    return finding_payload(db, row)


@router.patch("/audit-findings/{finding_id}")
def patch_finding(
    finding_id: int,
    title: str | None = Form(None),
    condition: str | None = Form(None),
    criteria: str | None = Form(None),
    cause: str | None = Form(None),
    effect_risk: str | None = Form(None),
    recommendation: str | None = Form(None),
    severity: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = _finding_for_user(db, finding_id, user)
    update_finding(
        db, row, title=title, condition=condition, criteria=criteria, cause=cause,
        effect_risk=effect_risk, recommendation=recommendation, severity=severity, user=user,
    )
    db.commit()
    db.refresh(row)
    return finding_payload(db, row)


@router.post("/audit-findings/{finding_id}/transition")
def post_finding_transition(
    finding_id: int,
    status: str = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER")),
):
    row = _finding_for_user(db, finding_id, user)
    transition_finding(db, row, target_status=status, user=user)
    db.commit()
    db.refresh(row)
    return finding_payload(db, row)


@router.post("/audit-findings/{finding_id}/reopen")
def post_finding_reopen(
    finding_id: int,
    reason: str = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "REVIEWER")),
):
    row = _finding_for_user(db, finding_id, user)
    reopen_finding(db, row, reason=reason, user=user)
    db.commit()
    db.refresh(row)
    return finding_payload(db, row)


@router.post("/audit-findings/{finding_id}/working-papers")
def post_finding_working_paper(
    finding_id: int,
    working_paper_id: int = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = _finding_for_user(db, finding_id, user)
    link_working_paper(db, row, working_paper_id=working_paper_id, user=user)
    db.commit()
    return finding_payload(db, row)


@router.post("/audit-findings/{finding_id}/evidence")
def post_finding_evidence(
    finding_id: int,
    document_id: int | None = Form(None),
    control_evidence_id: int | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = _finding_for_user(db, finding_id, user)
    link_evidence(db, row, document_id=document_id, control_evidence_id=control_evidence_id, user=user)
    db.commit()
    return finding_payload(db, row)


@router.post("/audit-findings/{finding_id}/exceptions")
def post_finding_exception(
    finding_id: int,
    audit_exception_id: int = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = _finding_for_user(db, finding_id, user)
    link_exception(db, row, audit_exception_id=audit_exception_id, user=user)
    db.commit()
    return finding_payload(db, row)


@router.post("/audit-findings/{finding_id}/samples")
def post_finding_sample(
    finding_id: int,
    sample_id: int = Form(...),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = _finding_for_user(db, finding_id, user)
    link_sample(db, row, sample_id=sample_id, user=user)
    db.commit()
    return finding_payload(db, row)


@router.delete("/audit-findings/{finding_id}/working-papers/{working_paper_id}")
def delete_finding_working_paper(
    finding_id: int,
    working_paper_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = _finding_for_user(db, finding_id, user)
    link = db.scalar(select(AuditFindingWorkingPaper).where(AuditFindingWorkingPaper.finding_id == row.id, AuditFindingWorkingPaper.working_paper_id == working_paper_id))
    _unlink(db, row, link, action="UNLINK_WORKING_PAPER", metadata={"working_paper_id": working_paper_id}, user=user)
    db.commit()
    return finding_payload(db, row)


@router.delete("/audit-findings/{finding_id}/evidence/{link_id}")
def delete_finding_evidence(
    finding_id: int,
    link_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = _finding_for_user(db, finding_id, user)
    link = db.get(AuditFindingEvidence, link_id)
    metadata = {"document_id": link.document_id, "control_evidence_id": link.control_evidence_id} if link else {"link_id": link_id}
    _unlink(db, row, link, action="UNLINK_EVIDENCE", metadata=metadata, user=user)
    db.commit()
    return finding_payload(db, row)


@router.delete("/audit-findings/{finding_id}/exceptions/{audit_exception_id}")
def delete_finding_exception(
    finding_id: int,
    audit_exception_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = _finding_for_user(db, finding_id, user)
    link = db.scalar(select(AuditFindingException).where(AuditFindingException.finding_id == row.id, AuditFindingException.audit_exception_id == audit_exception_id))
    _unlink(db, row, link, action="UNLINK_EXCEPTION", metadata={"audit_exception_id": audit_exception_id}, user=user)
    db.commit()
    return finding_payload(db, row)


@router.delete("/audit-findings/{finding_id}/samples/{sample_id}")
def delete_finding_sample(
    finding_id: int,
    sample_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = _finding_for_user(db, finding_id, user)
    link = db.scalar(select(AuditFindingSample).where(AuditFindingSample.finding_id == row.id, AuditFindingSample.sample_id == sample_id))
    _unlink(db, row, link, action="UNLINK_SAMPLE", metadata={"sample_id": sample_id}, user=user)
    db.commit()
    return finding_payload(db, row)


def register_audit_finding_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
