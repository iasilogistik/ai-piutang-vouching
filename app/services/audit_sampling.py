from __future__ import annotations

import json
from decimal import Decimal
from html import escape

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.auth import CurrentUser, require_roles
from app.branch_access import ensure_branch_access, normalize_branch, scoped_branch
from app.database import SessionLocal
from app.models import AuditEngagement, AuditPopulation, AuditSample, DocumentControlEvidence, VouchingResult

router = APIRouter()
_REGISTERED = False

SELECTION_METHODS = {"MANUAL", "RANDOM", "HIGH_VALUE", "RISK_BASED", "SYSTEM"}
SAMPLE_STATUSES = {"SELECTED", "IN_PROGRESS", "COMPLETED", "EXCLUDED"}


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _engagement_for_user(db: Session, engagement_id: int, user: CurrentUser) -> AuditEngagement:
    row = db.get(AuditEngagement, engagement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit engagement not found")
    ensure_branch_access(user, row.branch)
    return row


def population_payload(db: Session, row: AuditPopulation) -> dict[str, object]:
    sample_count = db.scalar(
        select(func.count(AuditSample.id)).where(
            AuditSample.population_id == row.id,
            AuditSample.status != "EXCLUDED",
        )
    ) or 0
    sampled_value = db.scalar(
        select(func.coalesce(func.sum(AuditSample.monetary_value), 0)).where(
            AuditSample.population_id == row.id,
            AuditSample.status != "EXCLUDED",
        )
    )
    record_coverage = (sample_count / row.total_records * 100) if row.total_records else 0.0
    value_coverage = None
    if row.total_value not in (None, 0):
        value_coverage = float((Decimal(sampled_value or 0) / Decimal(row.total_value)) * Decimal("100"))
    return {
        "id": row.id,
        "engagement_id": row.engagement_id,
        "branch": row.branch,
        "name": row.name,
        "population_type": row.population_type,
        "source_type": row.source_type,
        "source_reference": row.source_reference,
        "total_records": row.total_records,
        "total_value": str(row.total_value) if row.total_value is not None else None,
        "snapshot_at": row.snapshot_at.isoformat() if row.snapshot_at else None,
        "sample_count": int(sample_count),
        "record_coverage_pct": round(record_coverage, 2),
        "sampled_value": str(sampled_value or 0),
        "value_coverage_pct": round(value_coverage, 2) if value_coverage is not None else None,
    }


def sample_payload(row: AuditSample) -> dict[str, object]:
    return {
        "id": row.id,
        "engagement_id": row.engagement_id,
        "population_id": row.population_id,
        "branch": row.branch,
        "source_record_ref": row.source_record_ref,
        "selection_method": row.selection_method,
        "selection_reason": row.selection_reason,
        "method_parameters": row.method_parameters,
        "monetary_value": str(row.monetary_value) if row.monetary_value is not None else None,
        "status": row.status,
        "selected_by": row.selected_by,
        "selected_at": row.selected_at.isoformat() if row.selected_at else None,
        "vouching_result_id": row.vouching_result_id,
        "control_evidence_id": row.control_evidence_id,
    }


def create_population(
    db: Session,
    *,
    engagement: AuditEngagement,
    name: str,
    population_type: str,
    source_type: str,
    source_reference: str | None,
    total_records: int,
    total_value: Decimal | None,
    user: CurrentUser,
) -> AuditPopulation:
    if engagement.status == "CLOSED":
        raise HTTPException(status_code=409, detail="Closed engagement cannot receive a new population")
    if total_records < 0:
        raise HTTPException(status_code=400, detail="total_records cannot be negative")
    if total_value is not None and total_value < 0:
        raise HTTPException(status_code=400, detail="total_value cannot be negative")
    name = name.strip()
    population_type = population_type.strip().upper()
    source_type = source_type.strip().upper()
    if not name or not population_type or not source_type:
        raise HTTPException(status_code=400, detail="name, population_type and source_type are required")
    row = AuditPopulation(
        engagement_id=engagement.id,
        branch=engagement.branch,
        name=name,
        population_type=population_type,
        source_type=source_type,
        source_reference=(source_reference or "").strip() or None,
        total_records=total_records,
        total_value=total_value,
        created_by=user.user_id,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        entity_type="AUDIT_POPULATION",
        entity_id=row.id,
        action="CREATE",
        actor=user.user_id,
        branch=row.branch,
        metadata={
            "engagement_id": engagement.id,
            "total_records": total_records,
            "total_value": str(total_value) if total_value is not None else None,
            "source_type": source_type,
            "source_reference": row.source_reference,
        },
    )
    db.flush()
    return row


def select_sample(
    db: Session,
    *,
    population: AuditPopulation,
    source_record_ref: str,
    selection_method: str,
    selection_reason: str | None,
    method_parameters: dict | None,
    monetary_value: Decimal | None,
    user: CurrentUser,
) -> AuditSample:
    ensure_branch_access(user, population.branch)
    method = selection_method.strip().upper()
    if method not in SELECTION_METHODS:
        raise HTTPException(status_code=400, detail="Invalid selection_method")
    ref = source_record_ref.strip()
    if not ref:
        raise HTTPException(status_code=400, detail="source_record_ref is required")
    if monetary_value is not None and monetary_value < 0:
        raise HTTPException(status_code=400, detail="monetary_value cannot be negative")
    duplicate = db.scalar(
        select(AuditSample.id).where(
            AuditSample.population_id == population.id,
            AuditSample.source_record_ref == ref,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Sample already exists for this population record")
    row = AuditSample(
        engagement_id=population.engagement_id,
        population_id=population.id,
        branch=population.branch,
        source_record_ref=ref,
        selection_method=method,
        selection_reason=(selection_reason or "").strip() or None,
        method_parameters=method_parameters,
        monetary_value=monetary_value,
        status="SELECTED",
        selected_by=user.user_id,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        entity_type="AUDIT_SAMPLE",
        entity_id=row.id,
        action="SELECT",
        actor=user.user_id,
        status_to="SELECTED",
        branch=row.branch,
        metadata={
            "engagement_id": row.engagement_id,
            "population_id": row.population_id,
            "source_record_ref": row.source_record_ref,
            "selection_method": row.selection_method,
        },
    )
    db.flush()
    return row


def link_sample(
    db: Session,
    row: AuditSample,
    *,
    vouching_result_id: int | None,
    control_evidence_id: int | None,
    user: CurrentUser,
) -> AuditSample:
    ensure_branch_access(user, row.branch)
    if vouching_result_id is not None:
        vouch = db.get(VouchingResult, vouching_result_id)
        if vouch is None:
            raise HTTPException(status_code=404, detail="Vouching result not found")
        vouch_branch = vouch.billing.document.branch
        if normalize_branch(vouch_branch) != normalize_branch(row.branch):
            raise HTTPException(status_code=404, detail="Vouching result not found")
        row.vouching_result_id = vouch.id
    if control_evidence_id is not None:
        evidence = db.get(DocumentControlEvidence, control_evidence_id)
        if evidence is None:
            raise HTTPException(status_code=404, detail="Control evidence not found")
        evidence_branch = evidence.document.branch
        if normalize_branch(evidence_branch) != normalize_branch(row.branch):
            raise HTTPException(status_code=404, detail="Control evidence not found")
        row.control_evidence_id = evidence.id
    record_audit(
        db,
        entity_type="AUDIT_SAMPLE",
        entity_id=row.id,
        action="LINK_EVIDENCE",
        actor=user.user_id,
        branch=row.branch,
        metadata={
            "vouching_result_id": row.vouching_result_id,
            "control_evidence_id": row.control_evidence_id,
        },
    )
    db.flush()
    return row


def _html() -> str:
    methods = "".join(f"<option>{escape(x)}</option>" for x in sorted(SELECTION_METHODS))
    return f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit Sampling - AI Piutang Vouching</title>
<style>
body{{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}}header{{background:#0f172a;color:white;padding:18px 24px}}
main{{max-width:1180px;margin:auto;padding:20px}}.panel{{background:white;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}}
.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}input,select,button{{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}}
button{{background:#1f6feb;color:white;font-weight:700;cursor:pointer}}table{{width:100%;border-collapse:collapse}}th,td{{padding:8px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:12px}}
pre{{white-space:pre-wrap;background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px}}@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>Audit Population & Sampling</h1><p>Population snapshot, traceable selection, dan coverage audit.</p></header><main>
<section class="panel"><div class="grid"><input id="token" type="password" placeholder="Bearer token"><input id="engagementFilter" type="number" placeholder="Engagement ID"><button id="load">Muat Data</button></div></section>
<section class="panel"><h2>Buat Population Snapshot</h2><div class="grid"><input id="engagementId" type="number" placeholder="Engagement ID"><input id="populationName" placeholder="Nama populasi"><input id="populationType" placeholder="Jenis populasi"><input id="sourceType" placeholder="Source type"><input id="sourceReference" placeholder="Source/import reference"><input id="totalRecords" type="number" min="0" placeholder="Total records"><input id="totalValue" type="number" min="0" step="0.01" placeholder="Total value"><button id="createPopulation">Buat Population</button></div></section>
<section class="panel"><h2>Pilih Sample</h2><div class="grid"><input id="populationId" type="number" placeholder="Population ID"><input id="recordRef" placeholder="Source record ref"><select id="method">{methods}</select><input id="reason" placeholder="Selection reason"><input id="sampleValue" type="number" min="0" step="0.01" placeholder="Monetary value"><button id="selectSample">Pilih Sample</button></div></section>
<section class="panel"><table><thead><tr><th>Population</th><th>Engagement</th><th>Records</th><th>Samples</th><th>Coverage</th><th>Value Coverage</th></tr></thead><tbody id="rows"><tr><td colspan="6">Belum dimuat.</td></tr></tbody></table></section>
<section class="panel"><pre id="log">Belum ada aktivitas.</pre></section></main>
<script>
const token=document.getElementById('token');token.value=localStorage.getItem('auditToken')||'';
const log=document.getElementById('log');const rows=document.getElementById('rows');
function headers(){{const v=token.value.trim();if(!v)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',v);return {{Authorization:'Bearer '+v}}}}
async function jsonReq(url,opt={{}}){{opt.headers=Object.assign({{}},opt.headers||{{}},headers());const r=await fetch(url,opt);const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));log.textContent=JSON.stringify(x,null,2);return x}}
async function loadData(){{const id=document.getElementById('engagementFilter').value;const p=new URLSearchParams();if(id)p.set('engagement_id',id);const x=await jsonReq('/audit-populations?'+p);rows.innerHTML=(x.populations||[]).map(v=>'<tr><td>'+v.id+' - '+v.name+'</td><td>'+v.engagement_id+'</td><td>'+v.total_records+'</td><td>'+v.sample_count+'</td><td>'+v.record_coverage_pct+'%</td><td>'+(v.value_coverage_pct===null?'-':v.value_coverage_pct+'%')+'</td></tr>').join('')||'<tr><td colspan="6">Tidak ada populasi.</td></tr>'}}
async function post(url,data){{const fd=new FormData();Object.entries(data).forEach(([k,v])=>{{if(v!==''&&v!=null)fd.append(k,v)}});return jsonReq(url,{{method:'POST',body:fd}})}}
document.getElementById('load').onclick=()=>loadData().catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('createPopulation').onclick=()=>post('/audit-populations',{{engagement_id:document.getElementById('engagementId').value,name:document.getElementById('populationName').value,population_type:document.getElementById('populationType').value,source_type:document.getElementById('sourceType').value,source_reference:document.getElementById('sourceReference').value,total_records:document.getElementById('totalRecords').value,total_value:document.getElementById('totalValue').value}}).then(loadData).catch(e=>log.textContent='ERROR: '+e.message);
document.getElementById('selectSample').onclick=()=>post('/audit-samples',{{population_id:document.getElementById('populationId').value,source_record_ref:document.getElementById('recordRef').value,selection_method:document.getElementById('method').value,selection_reason:document.getElementById('reason').value,monetary_value:document.getElementById('sampleValue').value}}).then(loadData).catch(e=>log.textContent='ERROR: '+e.message);
</script></body></html>"""


@router.get("/ui/audit-sampling", response_class=HTMLResponse)
def audit_sampling_ui():
    return HTMLResponse(_html())


@router.get("/audit-populations")
def get_populations(
    engagement_id: int | None = None,
    branch: str | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    query = select(AuditPopulation).order_by(AuditPopulation.id.desc())
    if effective_branch is not None:
        query = query.where(AuditPopulation.branch == effective_branch)
    if engagement_id is not None:
        engagement = _engagement_for_user(db, engagement_id, user)
        query = query.where(AuditPopulation.engagement_id == engagement.id)
    rows = list(db.scalars(query).all())
    return {"total": len(rows), "populations": [population_payload(db, row) for row in rows]}


@router.get("/audit-populations/{population_id}/samples")
def get_samples(
    population_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    population = db.get(AuditPopulation, population_id)
    if population is None:
        raise HTTPException(status_code=404, detail="Audit population not found")
    ensure_branch_access(user, population.branch)
    rows = list(
        db.scalars(
            select(AuditSample).where(AuditSample.population_id == population.id).order_by(AuditSample.id)
        ).all()
    )
    return {
        "population": population_payload(db, population),
        "samples": [sample_payload(row) for row in rows],
    }


@router.post("/audit-populations")
def post_population(
    engagement_id: int = Form(...),
    name: str = Form(...),
    population_type: str = Form(...),
    source_type: str = Form(...),
    source_reference: str | None = Form(None),
    total_records: int = Form(...),
    total_value: Decimal | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    engagement = _engagement_for_user(db, engagement_id, user)
    row = create_population(
        db,
        engagement=engagement,
        name=name,
        population_type=population_type,
        source_type=source_type,
        source_reference=source_reference,
        total_records=total_records,
        total_value=total_value,
        user=user,
    )
    db.commit()
    db.refresh(row)
    return population_payload(db, row)


@router.post("/audit-samples")
def post_sample(
    population_id: int = Form(...),
    source_record_ref: str = Form(...),
    selection_method: str = Form(...),
    selection_reason: str | None = Form(None),
    method_parameters: str | None = Form(None),
    monetary_value: Decimal | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    population = db.get(AuditPopulation, population_id)
    if population is None:
        raise HTTPException(status_code=404, detail="Audit population not found")
    ensure_branch_access(user, population.branch)
    params = None
    if method_parameters:
        try:
            params = json.loads(method_parameters)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="method_parameters must be valid JSON") from exc
        if not isinstance(params, dict):
            raise HTTPException(status_code=400, detail="method_parameters must be a JSON object")
    row = select_sample(
        db,
        population=population,
        source_record_ref=source_record_ref,
        selection_method=selection_method,
        selection_reason=selection_reason,
        method_parameters=params,
        monetary_value=monetary_value,
        user=user,
    )
    db.commit()
    db.refresh(row)
    return sample_payload(row)


@router.post("/audit-samples/{sample_id}/link")
def post_sample_link(
    sample_id: int,
    vouching_result_id: int | None = Form(None),
    control_evidence_id: int | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR")),
):
    row = db.get(AuditSample, sample_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Audit sample not found")
    link_sample(
        db,
        row,
        vouching_result_id=vouching_result_id,
        control_evidence_id=control_evidence_id,
        user=user,
    )
    db.commit()
    db.refresh(row)
    return sample_payload(row)


def register_audit_sampling_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
