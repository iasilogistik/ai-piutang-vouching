from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_roles
from app.branch_access import normalize_branch, scoped_branch
from app.database import SessionLocal
from app.models import (
    AuditEngagement,
    AuditEngagementAssignment,
    AuditFinding,
    AuditSample,
    AuditWorkingPaper,
    CorrectiveActionPlan,
)

router = APIRouter()
_REGISTERED = False


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 1) if denominator else 0.0


def _aging_bucket(days: int) -> str:
    if days <= 7:
        return "0-7"
    if days <= 30:
        return "8-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "91+"


def _query_string(**kwargs) -> str:
    return urlencode({k: v for k, v in kwargs.items() if v not in (None, "")})


def build_audit_management_dashboard(
    db: Session,
    *,
    branch: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    engagement_id: int | None = None,
    auditor_id: str | None = None,
    reviewer_id: str | None = None,
    pic_user_id: str | None = None,
    engagement_status: str | None = None,
    finding_status: str | None = None,
    action_status: str | None = None,
    severity: str | None = None,
    as_of: date | None = None,
) -> dict[str, object]:
    today = as_of or _utc_today()

    engagement_q = select(AuditEngagement).order_by(AuditEngagement.period_start.desc(), AuditEngagement.id.desc())
    if branch:
        engagement_q = engagement_q.where(AuditEngagement.branch == normalize_branch(branch))
    if date_from:
        engagement_q = engagement_q.where(AuditEngagement.period_end >= date_from)
    if date_to:
        engagement_q = engagement_q.where(AuditEngagement.period_start <= date_to)
    if engagement_id is not None:
        engagement_q = engagement_q.where(AuditEngagement.id == engagement_id)
    if engagement_status:
        engagement_q = engagement_q.where(AuditEngagement.status == engagement_status.strip().upper())

    engagements = list(db.scalars(engagement_q).all())

    if auditor_id:
        allowed = set(
            db.scalars(
                select(AuditEngagementAssignment.engagement_id).where(
                    AuditEngagementAssignment.assignment_role == "AUDITOR",
                    AuditEngagementAssignment.user_id == auditor_id.strip(),
                )
            ).all()
        )
        engagements = [x for x in engagements if x.id in allowed]
    if reviewer_id:
        allowed = set(
            db.scalars(
                select(AuditEngagementAssignment.engagement_id).where(
                    AuditEngagementAssignment.assignment_role == "REVIEWER",
                    AuditEngagementAssignment.user_id == reviewer_id.strip(),
                )
            ).all()
        )
        engagements = [x for x in engagements if x.id in allowed]

    engagement_ids = [x.id for x in engagements]

    assignments = []
    if engagement_ids:
        assignments = list(
            db.scalars(
                select(AuditEngagementAssignment).where(
                    AuditEngagementAssignment.engagement_id.in_(engagement_ids)
                )
            ).all()
        )

    samples = []
    working_papers = []
    findings = []
    if engagement_ids:
        samples = list(
            db.scalars(select(AuditSample).where(AuditSample.engagement_id.in_(engagement_ids))).all()
        )
        working_papers = list(
            db.scalars(
                select(AuditWorkingPaper).where(AuditWorkingPaper.engagement_id.in_(engagement_ids))
            ).all()
        )
        finding_q = select(AuditFinding).where(AuditFinding.engagement_id.in_(engagement_ids))
        if finding_status:
            finding_q = finding_q.where(AuditFinding.status == finding_status.strip().upper())
        if severity:
            finding_q = finding_q.where(AuditFinding.severity == severity.strip().upper())
        findings = list(db.scalars(finding_q).all())

    finding_ids = [x.id for x in findings]
    action_plans = []
    if finding_ids:
        action_q = select(CorrectiveActionPlan).where(CorrectiveActionPlan.finding_id.in_(finding_ids))
        if pic_user_id:
            action_q = action_q.where(CorrectiveActionPlan.pic_user_id == pic_user_id.strip())
        if action_status:
            action_q = action_q.where(CorrectiveActionPlan.status == action_status.strip().upper())
        action_plans = list(db.scalars(action_q).all())

    engagement_statuses = Counter(x.status for x in engagements)
    wp_statuses = Counter(x.status for x in working_papers)
    finding_severity = Counter(x.severity for x in findings)
    finding_statuses = Counter(x.status for x in findings)
    action_statuses = Counter(x.status for x in action_plans)

    completed_engagements = sum(engagement_statuses.get(x, 0) for x in ("COMPLETED", "CLOSED"))
    reviewed_wps = wp_statuses.get("REVIEWED", 0)

    open_plans = [x for x in action_plans if x.status != "CLOSED"]
    overdue_plans = [x for x in open_plans if x.target_date < today]
    due_soon_plans = [
        x for x in open_plans
        if today <= x.target_date <= today + timedelta(days=7)
    ]
    awaiting_verification = [x for x in action_plans if x.status == "SUBMITTED_FOR_VERIFICATION"]
    closed_plans = [x for x in action_plans if x.status == "CLOSED"]

    branch_distribution: dict[str, dict[str, int]] = defaultdict(lambda: {
        "engagements": 0, "findings": 0, "action_plans": 0
    })
    for x in engagements:
        branch_distribution[x.branch]["engagements"] += 1
    for x in findings:
        branch_distribution[x.branch]["findings"] += 1
    for x in action_plans:
        branch_distribution[x.branch]["action_plans"] += 1

    pic_workload = Counter()
    for x in open_plans:
        label = x.pic_user_id or x.external_pic_name or "UNASSIGNED"
        pic_workload[label] += 1

    aging_buckets = Counter()
    for x in open_plans:
        created = x.created_at.date() if x.created_at else today
        aging_buckets[_aging_bucket(max((today - created).days, 0))] += 1

    auditor_workload = Counter()
    reviewer_workload = Counter()
    for a in assignments:
        if a.assignment_role == "AUDITOR":
            auditor_workload[a.user_id] += 1
        elif a.assignment_role == "REVIEWER":
            reviewer_workload[a.user_id] += 1

    filters = {
        "branch": branch,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "engagement_id": engagement_id,
        "auditor_id": auditor_id,
        "reviewer_id": reviewer_id,
        "pic_user_id": pic_user_id,
        "engagement_status": engagement_status.upper() if engagement_status else None,
        "finding_status": finding_status.upper() if finding_status else None,
        "action_status": action_status.upper() if action_status else None,
        "severity": severity.upper() if severity else None,
        "as_of": today.isoformat(),
    }

    downstream = {
        "branch": branch,
        "engagement_id": engagement_id,
    }
    if severity:
        downstream["severity"] = severity.upper()
    if finding_status:
        downstream["status"] = finding_status.upper()

    return {
        "filters": filters,
        "metrics": {
            "engagements_total": len(engagements),
            "engagements_completed": completed_engagements,
            "engagement_completion_pct": _pct(completed_engagements, len(engagements)),
            "samples_total": len(samples),
            "working_papers_total": len(working_papers),
            "working_papers_reviewed": reviewed_wps,
            "working_paper_review_pct": _pct(reviewed_wps, len(working_papers)),
            "findings_total": len(findings),
            "open_action_plans": len(open_plans),
            "due_soon": len(due_soon_plans),
            "overdue": len(overdue_plans),
            "awaiting_verification": len(awaiting_verification),
            "closed_follow_ups": len(closed_plans),
        },
        "distributions": {
            "engagement_status": dict(sorted(engagement_statuses.items())),
            "working_paper_status": dict(sorted(wp_statuses.items())),
            "finding_severity": dict(sorted(finding_severity.items())),
            "finding_status": dict(sorted(finding_statuses.items())),
            "action_plan_status": dict(sorted(action_statuses.items())),
            "branch": dict(sorted(branch_distribution.items())),
            "pic_workload_open": dict(sorted(pic_workload.items())),
            "auditor_engagement_workload": dict(sorted(auditor_workload.items())),
            "reviewer_engagement_workload": dict(sorted(reviewer_workload.items())),
            "open_action_plan_aging": {
                key: aging_buckets.get(key, 0)
                for key in ("0-7", "8-30", "31-60", "61-90", "91+")
            },
        },
        "metric_definitions": {
            "engagements_completed": "Engagements with status COMPLETED or CLOSED.",
            "engagement_completion_pct": "engagements_completed / engagements_total * 100.",
            "working_papers_reviewed": "Working papers with status REVIEWED.",
            "working_paper_review_pct": "working_papers_reviewed / working_papers_total * 100.",
            "open_action_plans": "Corrective action plans whose status is not CLOSED.",
            "due_soon": "Non-CLOSED plans with target date from as_of through as_of + 7 calendar days.",
            "overdue": "Non-CLOSED plans with target date earlier than as_of.",
            "awaiting_verification": "Plans with status SUBMITTED_FOR_VERIFICATION.",
            "closed_follow_ups": "Plans with status CLOSED.",
            "open_action_plan_aging": "Non-CLOSED plans bucketed by calendar days from created_at date to as_of.",
        },
        "drilldowns": {
            "engagements": "/audit-engagements?" + _query_string(
                branch=branch, status=engagement_status
            ),
            "working_papers": "/audit-working-papers?" + _query_string(
                branch=branch, engagement_id=engagement_id
            ),
            "findings": "/audit-findings?" + _query_string(**downstream),
            "action_plans": "/follow-up?" + _query_string(
                branch=branch, engagement_id=engagement_id, pic_user_id=pic_user_id,
                status=action_status, severity=severity
            ),
            "overdue": "/follow-up?" + _query_string(
                branch=branch, engagement_id=engagement_id, pic_user_id=pic_user_id,
                overdue="true", severity=severity
            ),
            "awaiting_verification": "/follow-up?" + _query_string(
                branch=branch, engagement_id=engagement_id, pic_user_id=pic_user_id,
                status="SUBMITTED_FOR_VERIFICATION", severity=severity
            ),
        },
    }


def _html() -> str:
    return """<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit Management Dashboard</title><style>
body{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}header{background:#0f172a;color:#fff;padding:18px 24px}main{max-width:1240px;margin:auto;padding:20px}
.panel{background:#fff;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
input,select,button{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}button{background:#1f6feb;color:#fff;font-weight:700}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.kpi{border:1px solid #e2e8f0;border-radius:10px;padding:12px}.kpi strong{display:block;font-size:24px}
pre{white-space:pre-wrap;background:#0f172a;color:#dbeafe;padding:12px;border-radius:10px}@media(max-width:850px){.grid,.kpis{grid-template-columns:1fr}}</style></head><body>
<header><h1>Audit Management Dashboard</h1><p>Portfolio audit branch-aware dari engagement sampai follow-up.</p></header><main>
<section class="panel"><div class="grid">
<input id="token" type="password" placeholder="Bearer token"><input id="branch" placeholder="Branch (ADMIN: kosong = semua)">
<input id="from" type="date"><input id="to" type="date"><input id="engagement" type="number" placeholder="Engagement ID">
<input id="auditor" placeholder="Auditor user ID"><input id="reviewer" placeholder="Reviewer user ID"><input id="pic" placeholder="PIC user ID">
<select id="severity"><option value="">All severity</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select>
<select id="actionStatus"><option value="">All action status</option><option>OPEN</option><option>IN_PROGRESS</option><option>SUBMITTED_FOR_VERIFICATION</option><option>VERIFIED</option><option>CLOSED</option><option>RETURNED</option><option>REOPENED</option></select>
<button id="load">Muat Dashboard</button></div></section>
<section class="panel"><div class="kpis" id="kpis"></div></section>
<section class="panel"><pre id="detail">Belum dimuat.</pre></section></main>
<script>
const token=document.getElementById('token');token.value=localStorage.getItem('auditToken')||'';
function headers(){const v=token.value.trim();if(!v)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',v);return {Authorization:'Bearer '+v}}
async function load(){const p=new URLSearchParams();for(const [id,key] of [['branch','branch'],['from','date_from'],['to','date_to'],['engagement','engagement_id'],['auditor','auditor_id'],['reviewer','reviewer_id'],['pic','pic_user_id'],['severity','severity'],['actionStatus','action_status']]){const v=document.getElementById(id).value.trim();if(v)p.set(key,v)}
const r=await fetch('/dashboard/audit-management?'+p,{headers:headers()});const x=await r.json();if(!r.ok){document.getElementById('detail').textContent=JSON.stringify(x,null,2);return}
const labels={engagements_total:'Engagements',engagement_completion_pct:'Engagement Complete %',working_papers_total:'Working Papers',working_paper_review_pct:'WP Reviewed %',findings_total:'Findings',open_action_plans:'Open Actions',due_soon:'Due Soon',overdue:'Overdue',awaiting_verification:'Awaiting Verification',closed_follow_ups:'Closed Follow-up'};
document.getElementById('kpis').innerHTML=Object.entries(x.metrics).filter(([k])=>labels[k]).map(([k,v])=>'<div class="kpi"><span>'+labels[k]+'</span><strong>'+v+'</strong></div>').join('');
document.getElementById('detail').textContent=JSON.stringify(x,null,2)}
document.getElementById('load').onclick=load;load().catch(e=>document.getElementById('detail').textContent='ERROR: '+e.message);
</script></body></html>"""


@router.get("/ui/audit-management", response_class=HTMLResponse)
def audit_management_ui():
    return HTMLResponse(_html())


@router.get("/dashboard/audit-management")
def audit_management_api(
    branch: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    engagement_id: int | None = None,
    auditor_id: str | None = None,
    reviewer_id: str | None = None,
    pic_user_id: str | None = None,
    engagement_status: str | None = None,
    finding_status: str | None = None,
    action_status: str | None = None,
    severity: str | None = None,
    as_of: date | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be before or equal to date_to")
    return build_audit_management_dashboard(
        db,
        branch=scoped_branch(user, branch),
        date_from=date_from,
        date_to=date_to,
        engagement_id=engagement_id,
        auditor_id=auditor_id,
        reviewer_id=reviewer_id,
        pic_user_id=pic_user_id,
        engagement_status=engagement_status,
        finding_status=finding_status,
        action_status=action_status,
        severity=severity,
        as_of=as_of,
    )


def register_audit_management_dashboard_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
