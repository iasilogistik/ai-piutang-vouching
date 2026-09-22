from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from html import escape

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.audit import AuditTrail
from app.auth import CurrentUser, require_roles
from app.branch_access import normalize_branch, scoped_branch
from app.database import SessionLocal
from app.models import (
    AuditClosing,
    AuditEngagementAssignment,
    AuditFinding,
    AuditNotification,
    AuditReport,
    CorrectiveActionPlan,
    NotificationPreference,
    ReviewWorkflow,
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


def _active_user(db: Session, user_id: str | None) -> bool:
    if not user_id:
        return False
    if db.get_bind().dialect.name == "sqlite":
        return True
    row = db.execute(
        text("select is_active from public.user_roles where cast(user_id as text)=:user_id"),
        {"user_id": user_id},
    ).scalar_one_or_none()
    return bool(row)


def _branch_role_users(db: Session, branch: str | None, role: str) -> set[str]:
    branch = normalize_branch(branch)
    if branch is None or db.get_bind().dialect.name == "sqlite":
        return set()
    rows = db.execute(
        text(
            """
            select cast(user_id as text) as user_id
            from public.user_roles
            where is_active = true
              and role::text = :role
              and upper(trim(branch)) = :branch
            """
        ),
        {"role": role, "branch": branch},
    ).scalars().all()
    return {str(x) for x in rows}


def _engagement_users(db: Session, engagement_id: int | None, role: str | None = None) -> set[str]:
    if engagement_id is None:
        return set()
    query = select(AuditEngagementAssignment.user_id).where(
        AuditEngagementAssignment.engagement_id == engagement_id
    )
    if role:
        query = query.where(AuditEngagementAssignment.assignment_role == role)
    return set(db.scalars(query).all())


def _preference(db: Session, user_id: str) -> NotificationPreference | None:
    return db.get(NotificationPreference, user_id)


def create_notification(
    db: Session,
    *,
    user_id: str,
    branch: str | None,
    event_type: str,
    title: str,
    message: str,
    target_type: str | None,
    target_id: int | None,
    target_url: str | None,
    idempotency_key: str,
) -> AuditNotification | None:
    if not _active_user(db, user_id):
        return None
    pref = _preference(db, user_id)
    if pref is not None and not pref.in_app_enabled:
        return None
    existing = db.scalar(
        select(AuditNotification).where(AuditNotification.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing
    row = AuditNotification(
        user_id=user_id,
        branch=normalize_branch(branch),
        event_type=event_type,
        title=title,
        message=message,
        target_type=target_type,
        target_id=target_id,
        target_url=target_url,
        idempotency_key=idempotency_key,
        is_read=False,
    )
    db.add(row)
    db.flush()
    return row


def _deliver(
    db: Session,
    *,
    entry: AuditTrail,
    recipients: set[str],
    event_type: str,
    title: str,
    message: str,
    target_url: str,
) -> list[AuditNotification]:
    rows: list[AuditNotification] = []
    for user_id in sorted(recipients):
        if not user_id or user_id == entry.actor:
            continue
        row = create_notification(
            db,
            user_id=user_id,
            branch=entry.branch,
            event_type=event_type,
            title=title,
            message=message,
            target_type=entry.entity_type,
            target_id=entry.entity_id,
            target_url=target_url,
            idempotency_key=f"audit:{entry.id}:user:{user_id}",
        )
        if row is not None:
            rows.append(row)
    return rows


def _finding_engagement(db: Session, finding_id: int | None) -> tuple[AuditFinding | None, int | None]:
    finding = db.get(AuditFinding, finding_id) if finding_id is not None else None
    return finding, finding.engagement_id if finding else None


def _plan_context(db: Session, plan_id: int | None) -> tuple[CorrectiveActionPlan | None, AuditFinding | None, int | None]:
    plan = db.get(CorrectiveActionPlan, plan_id) if plan_id is not None else None
    finding = db.get(AuditFinding, plan.finding_id) if plan else None
    return plan, finding, finding.engagement_id if finding else None


def _closing_engagement(db: Session, closing_id: int | None) -> tuple[AuditClosing | None, int | None]:
    closing = db.get(AuditClosing, closing_id) if closing_id is not None else None
    report = db.get(AuditReport, closing.audit_report_id) if closing else None
    return closing, report.engagement_id if report else None


def emit_from_audit_event(db: Session, entry: AuditTrail) -> list[AuditNotification]:
    metadata = entry.metadata_json or {}
    recipients: set[str] = set()
    event_type: str | None = None
    title = ""
    message = ""
    target_url = "/ui/dashboard"

    if entry.entity_type == "AUDIT_ENGAGEMENT" and entry.action == "ASSIGN":
        assigned = metadata.get("assigned_user_id")
        if assigned:
            recipients.add(str(assigned))
        event_type = "ASSIGNMENT"
        title = "Audit assignment"
        message = "You were assigned to an audit engagement."
        target_url = "/ui/audit-engagements"

    elif entry.entity_type == "REVIEW_WORKFLOW" and entry.action == "TRANSITION":
        row = db.get(ReviewWorkflow, entry.entity_id) if entry.entity_id is not None else None
        target_url = "/ui/review-queue"
        if entry.status_to == "AUDITOR_REVIEWED":
            if row and row.reviewer_id:
                recipients.add(row.reviewer_id)
            recipients |= _branch_role_users(db, entry.branch, "REVIEWER")
            event_type = "REVIEW_REQUESTED"
            title = "Review requested"
            message = "An audit item is ready for reviewer approval."
        elif entry.status_to == "REVIEWER_REJECTED":
            if row and row.auditor_id:
                recipients.add(row.auditor_id)
            event_type = "REVIEW_RETURNED"
            title = "Review returned"
            message = "A reviewed audit item was returned for rework."
        elif entry.status_to == "REVIEWER_APPROVED":
            if row and row.auditor_id:
                recipients.add(row.auditor_id)
            event_type = "REVIEW_APPROVED"
            title = "Review approved"
            message = "A reviewed audit item was approved."

    elif entry.entity_type == "AUDIT_FINDING":
        finding, engagement_id = _finding_engagement(db, entry.entity_id)
        target_url = "/ui/audit-findings"
        if entry.action == "TRANSITION" and entry.status_to == "ISSUED":
            recipients |= _engagement_users(db, engagement_id)
            event_type = "FINDING_ISSUED"
            title = "Audit finding issued"
            message = f"Finding {finding.reference if finding else entry.entity_id} has been issued."
        elif entry.action == "REOPEN":
            recipients |= _engagement_users(db, engagement_id, "AUDITOR")
            event_type = "FINDING_REOPENED"
            title = "Audit finding reopened"
            message = "An audit finding was reopened and requires follow-up."

    elif entry.entity_type == "CORRECTIVE_ACTION_PLAN":
        plan, finding, engagement_id = _plan_context(db, entry.entity_id)
        target_url = "/ui/follow-up"
        if plan and plan.pic_user_id:
            recipients.add(plan.pic_user_id)

        if entry.action == "CREATE":
            if not recipients:
                recipients |= _engagement_users(db, engagement_id, "AUDITOR")
            event_type = "ACTION_PLAN_ASSIGNED"
            title = "Corrective action assigned"
            message = "A corrective action plan has been assigned."
        elif entry.action in {"UPDATE", "FOLLOW_UP_PROGRESS"}:
            if entry.action == "FOLLOW_UP_PROGRESS":
                recipients |= _engagement_users(db, engagement_id, "AUDITOR")
            event_type = "ACTION_PLAN_UPDATED"
            title = "Corrective action updated"
            message = "A corrective action plan has new progress or changes."
        elif entry.action == "TRANSITION" and entry.status_to == "SUBMITTED_FOR_VERIFICATION":
            recipients = _engagement_users(db, engagement_id, "REVIEWER")
            if not recipients:
                recipients |= _branch_role_users(db, entry.branch, "REVIEWER")
            event_type = "SUBMITTED_FOR_VERIFICATION"
            title = "Action plan awaiting verification"
            message = "A corrective action plan was submitted for verification."
        elif entry.action == "TRANSITION" and entry.status_to == "REOPENED":
            recipients |= _engagement_users(db, engagement_id, "AUDITOR")
            event_type = "ACTION_PLAN_REOPENED"
            title = "Corrective action reopened"
            message = "A closed corrective action plan was reopened."
        elif entry.action == "FOLLOW_UP_VERIFICATION":
            result = str(metadata.get("result") or "").upper()
            recipients |= _engagement_users(db, engagement_id, "AUDITOR")
            if result == "RETURNED":
                event_type = "VERIFICATION_RETURNED"
                title = "Verification returned"
                message = "Corrective action verification was returned for additional work."
            elif result == "VERIFIED":
                event_type = "VERIFICATION_ACCEPTED"
                title = "Verification accepted"
                message = "Corrective action evidence was verified."

    elif entry.entity_type == "AUDIT_CLOSING" and entry.action == "TRANSITION":
        _, engagement_id = _closing_engagement(db, entry.entity_id)
        target_url = "/ui/audit-closing"
        if entry.status_to == "AUDITOR_SIGNED":
            recipients |= _engagement_users(db, engagement_id, "REVIEWER")
            event_type = "AUDITOR_SIGNOFF"
            title = "Auditor sign-off complete"
            message = "Audit closing is ready for reviewer sign-off."
        elif entry.status_to == "REVIEWER_SIGNED":
            recipients |= _engagement_users(db, engagement_id, "AUDITOR")
            event_type = "REVIEWER_SIGNOFF"
            title = "Reviewer sign-off complete"
            message = "Audit closing received reviewer sign-off."
        elif entry.status_to == "CLOSED":
            recipients |= _engagement_users(db, engagement_id)
            event_type = "AUDIT_CLOSED"
            title = "Audit closed"
            message = "The audit closing workflow is complete."

    if event_type is None or not recipients:
        return []
    return _deliver(
        db,
        entry=entry,
        recipients=recipients,
        event_type=event_type,
        title=title,
        message=message,
        target_url=target_url,
    )


def _reminder_recipients(db: Session, plan: CorrectiveActionPlan) -> set[str]:
    if plan.pic_user_id:
        return {plan.pic_user_id}
    finding = db.get(AuditFinding, plan.finding_id)
    return _engagement_users(db, finding.engagement_id if finding else None, "AUDITOR")


def generate_deadline_reminders(
    db: Session,
    *,
    as_of: date | None = None,
    branch: str | None = None,
) -> dict[str, int]:
    today = as_of or _utc_today()
    query = select(CorrectiveActionPlan).where(CorrectiveActionPlan.status != "CLOSED")
    if branch:
        query = query.where(CorrectiveActionPlan.branch == normalize_branch(branch))
    plans = list(db.scalars(query).all())
    created = {"due_soon": 0, "overdue": 0}

    for plan in plans:
        for user_id in _reminder_recipients(db, plan):
            pref = _preference(db, user_id)
            reminder_days = pref.reminder_days_before if pref else 7
            delta = (plan.target_date - today).days
            if plan.target_date < today:
                kind = "OVERDUE_REMINDER"
                title = "Corrective action overdue"
                message = f"Action plan #{plan.id} is overdue since {plan.target_date.isoformat()}."
                bucket = "overdue"
            elif 0 <= delta <= reminder_days:
                kind = "DUE_SOON_REMINDER"
                title = "Corrective action due soon"
                message = f"Action plan #{plan.id} is due on {plan.target_date.isoformat()}."
                bucket = "due_soon"
            else:
                continue

            before = db.scalar(
                select(AuditNotification.id).where(
                    AuditNotification.idempotency_key
                    == f"reminder:{kind}:plan:{plan.id}:user:{user_id}:date:{today.isoformat()}"
                )
            )
            row = create_notification(
                db,
                user_id=user_id,
                branch=plan.branch,
                event_type=kind,
                title=title,
                message=message,
                target_type="CORRECTIVE_ACTION_PLAN",
                target_id=plan.id,
                target_url="/ui/follow-up",
                idempotency_key=f"reminder:{kind}:plan:{plan.id}:user:{user_id}:date:{today.isoformat()}",
            )
            if row is not None and before is None:
                created[bucket] += 1
    return created


def notification_payload(row: AuditNotification) -> dict[str, object]:
    return {
        "id": row.id,
        "event_type": row.event_type,
        "title": row.title,
        "message": row.message,
        "branch": row.branch,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "target_url": row.target_url,
        "is_read": row.is_read,
        "read_at": row.read_at.isoformat() if row.read_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def unread_count(db: Session, user_id: str) -> int:
    return int(
        db.scalar(
            select(func.count(AuditNotification.id)).where(
                AuditNotification.user_id == user_id,
                AuditNotification.is_read.is_(False),
            )
        )
        or 0
    )


def _html() -> str:
    return """<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Audit Notifications</title><style>
body{font-family:Arial,sans-serif;margin:0;background:#f6f8fb;color:#182433}header{background:#0f172a;color:#fff;padding:18px 24px}main{max-width:1000px;margin:auto;padding:20px}
.panel{background:#fff;border:1px solid #d9e0ea;border-radius:12px;padding:16px;margin-bottom:14px}input,button{padding:8px;border:1px solid #cbd5e1;border-radius:8px;font:inherit}button{background:#1f6feb;color:#fff;font-weight:700}
.item{border-bottom:1px solid #e2e8f0;padding:12px 0}.unread{font-weight:700}.meta{font-size:12px;color:#64748b}</style></head><body>
<header><h1>Notification Inbox</h1><p>Audit assignments, reviews, findings, follow-up deadlines and sign-off events.</p></header><main>
<section class="panel"><input id="token" type="password" placeholder="Bearer token"><button id="load">Muat</button><button id="readAll">Mark all read</button></section>
<section class="panel"><div id="items">Belum dimuat.</div></section></main><script>
const token=document.getElementById('token');token.value=localStorage.getItem('auditToken')||'';
function headers(){const v=token.value.trim();if(!v)throw new Error('Bearer token wajib diisi');localStorage.setItem('auditToken',v);return {Authorization:'Bearer '+v}}
async function load(){const r=await fetch('/notifications',{headers:headers()});const x=await r.json();if(!r.ok)throw new Error(x.detail||JSON.stringify(x));document.getElementById('items').innerHTML=(x.notifications||[]).map(n=>'<div class="item '+(n.is_read?'':'unread')+'"><div>'+n.title+'</div><div>'+n.message+'</div><div class="meta">'+n.event_type+' · '+(n.created_at||'')+'</div>'+(n.target_url?'<a href="'+n.target_url+'">Open</a>':'')+' <button onclick="markRead('+n.id+')">Read</button></div>').join('')||'Tidak ada notifikasi.'}
async function markRead(id){await fetch('/notifications/'+id+'/read',{method:'POST',headers:headers()});await load()}
async function readAll(){await fetch('/notifications/read-all',{method:'POST',headers:headers()});await load()}
document.getElementById('load').onclick=()=>load();document.getElementById('readAll').onclick=()=>readAll();load().catch(()=>{});
</script></body></html>"""


@router.get("/ui/notifications", response_class=HTMLResponse)
def notifications_ui():
    return HTMLResponse(_html())


@router.get("/notifications")
def get_notifications(
    unread_only: bool = False,
    limit: int = 100,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    query = (
        select(AuditNotification)
        .where(AuditNotification.user_id == user.user_id)
        .order_by(AuditNotification.created_at.desc(), AuditNotification.id.desc())
        .limit(min(max(limit, 1), 250))
    )
    if unread_only:
        query = query.where(AuditNotification.is_read.is_(False))
    rows = list(db.scalars(query).all())
    return {
        "total": len(rows),
        "unread_count": unread_count(db, user.user_id),
        "notifications": [notification_payload(x) for x in rows],
    }


@router.get("/notifications/unread-count")
def get_unread_count(
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    return {"unread_count": unread_count(db, user.user_id)}


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    row = db.get(AuditNotification, notification_id)
    if row is None or row.user_id != user.user_id:
        raise HTTPException(status_code=404, detail="Notification not found")
    if not row.is_read:
        row.is_read = True
        row.read_at = datetime.now(timezone.utc)
        db.commit()
    return notification_payload(row)


@router.post("/notifications/read-all")
def mark_all_notifications_read(
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    rows = list(
        db.scalars(
            select(AuditNotification).where(
                AuditNotification.user_id == user.user_id,
                AuditNotification.is_read.is_(False),
            )
        ).all()
    )
    now = datetime.now(timezone.utc)
    for row in rows:
        row.is_read = True
        row.read_at = now
    db.commit()
    return {"updated": len(rows), "unread_count": 0}


@router.get("/notifications/preferences")
def get_notification_preferences(
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    row = db.get(NotificationPreference, user.user_id)
    return {
        "in_app_enabled": row.in_app_enabled if row else True,
        "email_enabled": row.email_enabled if row else False,
        "reminder_days_before": row.reminder_days_before if row else 7,
        "digest_frequency": row.digest_frequency if row else "IMMEDIATE",
    }


@router.post("/notifications/preferences")
def update_notification_preferences(
    in_app_enabled: bool = Form(True),
    email_enabled: bool = Form(False),
    reminder_days_before: int = Form(7),
    digest_frequency: str = Form("IMMEDIATE"),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")),
):
    frequency = digest_frequency.strip().upper()
    if not 0 <= reminder_days_before <= 30:
        raise HTTPException(status_code=400, detail="reminder_days_before must be between 0 and 30")
    if frequency not in {"IMMEDIATE", "DAILY", "WEEKLY"}:
        raise HTTPException(status_code=400, detail="Invalid digest_frequency")
    row = db.get(NotificationPreference, user.user_id)
    if row is None:
        row = NotificationPreference(user_id=user.user_id)
        db.add(row)
    row.in_app_enabled = in_app_enabled
    row.email_enabled = email_enabled
    row.reminder_days_before = reminder_days_before
    row.digest_frequency = frequency
    db.commit()
    return {
        "in_app_enabled": row.in_app_enabled,
        "email_enabled": row.email_enabled,
        "reminder_days_before": row.reminder_days_before,
        "digest_frequency": row.digest_frequency,
    }


@router.post("/notifications/reminders/run")
def run_notification_reminders(
    as_of: date | None = Form(None),
    branch: str | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN", "AUDITOR", "REVIEWER")),
):
    effective_branch = scoped_branch(user, branch)
    result = generate_deadline_reminders(db, as_of=as_of, branch=effective_branch)
    db.commit()
    return {"as_of": (as_of or _utc_today()).isoformat(), "branch": effective_branch, **result}


def register_notification_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
