from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.auth import CurrentUser, require_roles
from app.database import SessionLocal
from app.services.branch_master import normalize_branch_code, register_branch_master_routes

_ALLOWED_ROLES = {"ADMIN", "AUDITOR", "REVIEWER", "VIEWER"}
_REGISTERED = False
router = APIRouter()


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _serialize(row) -> dict[str, object]:
    return {
        "user_id": row["user_id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "branch": row["branch"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def _require_valid_role(role: str) -> str:
    role = role.upper().strip()
    if role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="role must be ADMIN, AUDITOR, REVIEWER, or VIEWER")
    return role


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _validated_active_branch(db: Session, branch: str | None) -> str | None:
    branch = _clean(branch)
    if branch is None:
        return None
    code = normalize_branch_code(branch)
    row = db.execute(
        text("select branch_code from public.branches where branch_code = :code and active = true"),
        {"code": code},
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=400, detail="branch must reference an active branch")
    return row["branch_code"]


def _users_html() -> str:
    return """
<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>User Management - AI Piutang Vouching</title>
  <style>
    :root { --bg:#f6f8fb; --card:#fff; --line:#d9e0ea; --text:#182433; --muted:#64748b; --blue:#1f6feb; --green:#188038; --red:#b3261e; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Arial, Helvetica, sans-serif; background:var(--bg); color:var(--text); }
    header { background:#0f172a; color:white; padding:18px 24px; }
    header h1 { margin:0; font-size:22px; }
    header p { margin:6px 0 0; color:#cbd5e1; }
    main { max-width:1180px; margin:0 auto; padding:20px 24px 40px; }
    .panel { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin:14px 0; box-shadow:0 1px 3px rgba(15,23,42,.06); }
    .grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
    label { display:block; font-size:12px; color:var(--muted); margin-bottom:5px; }
    input, select { width:100%; border:1px solid var(--line); border-radius:8px; padding:8px; font:inherit; background:white; }
    button, .button-link { border:0; border-radius:8px; padding:10px 13px; background:var(--blue); color:white; font-weight:700; cursor:pointer; text-decoration:none; display:inline-block; }
    button.secondary, .button-link.secondary { background:#475569; }
    button.danger { background:var(--red); }
    .actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; align-items:center; }
    table { width:100%; border-collapse:collapse; margin-top:10px; }
    th, td { border-bottom:1px solid var(--line); padding:8px; text-align:left; font-size:13px; vertical-align:top; }
    th { background:#f8fafc; }
    .ok { color:var(--green); font-weight:700; }
    .err { color:var(--red); font-weight:700; }
    .muted { color:var(--muted); font-size:13px; }
    pre { white-space:pre-wrap; word-break:break-word; background:#0f172a; color:#dbeafe; border-radius:10px; padding:12px; min-height:120px; max-height:360px; overflow:auto; }
    @media (max-width:800px) { .grid { grid-template-columns:1fr; } }
  </style>
</head>
<body>
<header>
  <h1>User Management</h1>
  <p>Kelola role aplikasi: ADMIN, AUDITOR, REVIEWER, dan VIEWER.</p>
</header>
<main>
  <section class="panel">
    <h2>Sesi Admin</h2>
    <p class="muted">Halaman ini memakai token login yang tersimpan otomatis di browser. Token tidak ditampilkan di layar.</p>
    <div class="actions">
      <button type="button" id="loadBtn">Muat User</button>
      <button type="button" class="secondary" id="logoutBtn">Logout</button>
      <a class="button-link secondary" href="/login">Login</a>
      <a class="button-link secondary" href="/ui/control-evidence">Control Evidence</a>
      <span id="sessionStatus" class="muted">Memeriksa sesi...</span>
    </div>
  </section>

  <section class="panel">
    <h2>Tambah / Ubah Role User</h2>
    <div class="grid">
      <div><label for="userId">User ID Supabase</label><input id="userId" placeholder="UUID user Supabase Auth" /></div>
      <div><label for="email">Email</label><input id="email" placeholder="nama@perusahaan.co.id" /></div>
      <div><label for="displayName">Nama</label><input id="displayName" placeholder="Nama user" /></div>
      <div><label for="role">Role</label><select id="role"><option>ADMIN</option><option>AUDITOR</option><option>REVIEWER</option><option>VIEWER</option></select></div>
      <div><label for="branch">Cabang</label><select id="branch"><option value="">-- ADMIN: tanpa cabang --</option></select></div>
      <div><label for="isActive">Status</label><select id="isActive"><option value="true">Aktif</option><option value="false">Nonaktif</option></select></div>
    </div>
    <div class="actions">
      <button type="button" id="saveBtn">Simpan User Role</button>
      <button type="button" class="secondary" id="clearBtn">Reset Form</button>
    </div>
  </section>

  <section class="panel">
    <h2>Daftar User</h2>
    <table>
      <thead><tr><th>User ID</th><th>Email</th><th>Nama</th><th>Role</th><th>Cabang</th><th>Status</th><th>Aksi</th></tr></thead>
      <tbody id="rows"><tr><td colspan="7">Belum dimuat.</td></tr></tbody>
    </table>
    <h3>Log</h3>
    <pre id="log">Belum ada aktivitas.</pre>
  </section>
</main>
<script>
const rowsEl = document.getElementById('rows');
const logEl = document.getElementById('log');
const sessionStatus = document.getElementById('sessionStatus');
function getAuditToken() {
  const token = localStorage.getItem('auditToken') || '';
  sessionStatus.textContent = token ? 'Sesi login tersedia.' : 'Belum login. Silakan login terlebih dahulu.';
  return token;
}
function authHeaders() {
  const token = getAuditToken();
  if (!token) {
    window.location.href = '/login';
    throw new Error('Silakan login sebagai ADMIN terlebih dahulu.');
  }
  return { Authorization: `Bearer ${token}` };
}
function appendLog(label, payload, ok = true) {
  const time = new Date().toISOString();
  const text = typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2);
  logEl.textContent = `[${time}] ${ok ? 'OK' : 'ERROR'} - ${label}\n${text}\n\n` + (logEl.textContent === 'Belum ada aktivitas.' ? '' : logEl.textContent);
}
async function loadBranches(selected = '') {
  try {
    const response = await fetch('/admin/branches?active=true', { headers: authHeaders() });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || JSON.stringify(body));
    const select = document.getElementById('branch');
    select.innerHTML = '<option value="">-- ADMIN: tanpa cabang --</option>' + (body.branches || []).map(
      branch => `<option value="${branch.branch_code}">${branch.branch_code} - ${branch.branch_name}</option>`
    ).join('');
    select.value = selected || '';
  } catch (error) { appendLog('Muat Master Cabang', error.message, false); }
}
function setForm(user) {
  document.getElementById('userId').value = user.user_id || '';
  document.getElementById('email').value = user.email || '';
  document.getElementById('displayName').value = user.display_name || '';
  document.getElementById('role').value = user.role || 'VIEWER';
  loadBranches(user.branch || '');
  document.getElementById('isActive').value = String(user.is_active !== false);
}
function render(users) {
  if (!users.length) { rowsEl.innerHTML = '<tr><td colspan="7">Belum ada user.</td></tr>'; return; }
  rowsEl.innerHTML = users.map(user => `<tr>
    <td>${user.user_id}</td><td>${user.email || '-'}</td><td>${user.display_name || '-'}</td>
    <td>${user.role}</td><td>${user.branch || '-'}</td><td class="${user.is_active ? 'ok' : 'err'}">${user.is_active ? 'Aktif' : 'Nonaktif'}</td>
    <td><button type="button" class="secondary" onclick='editUser(${JSON.stringify(user)})'>Edit</button> <button type="button" class="danger" onclick="deactivateUser('${user.user_id}')">Nonaktifkan</button></td>
  </tr>`).join('');
}
window.editUser = (user) => setForm(user);
async function loadUsers() {
  try {
    const response = await fetch('/admin/users', { headers: authHeaders() });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || JSON.stringify(body));
    await loadBranches(document.getElementById('branch').value);
    render(body.users || []);
    appendLog('Muat User', body);
  } catch (error) { appendLog('Muat User', error.message, false); }
}
async function saveUser() {
  try {
    const form = new FormData();
    form.append('user_id', document.getElementById('userId').value.trim());
    form.append('email', document.getElementById('email').value.trim());
    form.append('display_name', document.getElementById('displayName').value.trim());
    form.append('role', document.getElementById('role').value);
    form.append('branch', document.getElementById('branch').value.trim());
    form.append('is_active', document.getElementById('isActive').value);
    const response = await fetch('/admin/users', { method:'POST', headers: authHeaders(), body: form });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || JSON.stringify(body));
    appendLog('Simpan User Role', body);
    await loadUsers();
  } catch (error) { appendLog('Simpan User Role', error.message, false); }
}
window.deactivateUser = async (userId) => {
  try {
    const response = await fetch(`/admin/users/${encodeURIComponent(userId)}/deactivate`, { method:'POST', headers: authHeaders() });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || JSON.stringify(body));
    appendLog('Nonaktifkan User', body);
    await loadUsers();
  } catch (error) { appendLog('Nonaktifkan User', error.message, false); }
};
document.getElementById('loadBtn').addEventListener('click', loadUsers);
document.getElementById('saveBtn').addEventListener('click', saveUser);
document.getElementById('clearBtn').addEventListener('click', () => setForm({ role:'VIEWER', is_active:true }));
document.getElementById('logoutBtn').addEventListener('click', () => {
  localStorage.removeItem('auditToken');
  localStorage.removeItem('auditRefreshToken');
  localStorage.removeItem('auditExpiresAt');
  localStorage.removeItem('auditUser');
  window.location.href = '/login';
});
document.getElementById('role').addEventListener('change', () => {
  const branchSelect = document.getElementById('branch');
  if (document.getElementById('role').value !== 'ADMIN' && !branchSelect.value && branchSelect.options.length > 1) {
    branchSelect.selectedIndex = 1;
  }
});
if (getAuditToken()) {
  loadBranches();
} else {
  appendLog('Sesi Admin', 'Belum login. Token tidak ditampilkan di halaman ini.', false);
}
</script>
</body>
</html>
"""


@router.get("/ui/users", response_class=HTMLResponse)
def user_management_ui():
    return HTMLResponse(_users_html())


@router.get("/admin/users")
def list_users(db: Session = Depends(_db), user: CurrentUser = Depends(require_roles("ADMIN"))):
    rows = db.execute(
        text(
            """
            select user_id, email, display_name, role::text as role, branch, is_active, created_at, updated_at
            from public.user_roles
            order by created_at desc, email nulls last
            """
        )
    ).mappings().all()
    return {"total": len(rows), "users": [_serialize(row) for row in rows]}


@router.post("/admin/users")
def upsert_user_role(
    user_id: str = Form(...),
    email: str | None = Form(None),
    display_name: str | None = Form(None),
    role: str = Form("VIEWER"),
    branch: str | None = Form(None),
    is_active: bool = Form(True),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN")),
):
    user_id = user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    role = _require_valid_role(role)
    branch = _validated_active_branch(db, branch)
    if role != "ADMIN" and not branch:
        raise HTTPException(status_code=400, detail="branch is required for non-ADMIN users")

    previous = db.execute(
        text("select role::text as role, branch, is_active from public.user_roles where user_id = :user_id"),
        {"user_id": user_id},
    ).mappings().one_or_none()

    db.execute(
        text(
            """
            insert into public.user_roles (user_id, email, display_name, role, branch, is_active, updated_at)
            values (:user_id, :email, :display_name, :role, :branch, :is_active, now())
            on conflict (user_id) do update set
                email = excluded.email,
                display_name = excluded.display_name,
                role = excluded.role,
                branch = excluded.branch,
                is_active = excluded.is_active,
                updated_at = now()
            """
        ),
        {
            "user_id": user_id,
            "email": _clean(email),
            "display_name": _clean(display_name),
            "role": role,
            "branch": branch,
            "is_active": is_active,
        },
    )
    previous_branch = previous["branch"] if previous is not None else None
    action = "BRANCH_REASSIGN" if previous is not None and previous_branch != branch else "USER_ROLE_UPSERT"
    record_audit(
        db,
        entity_type="USER_ROLE",
        entity_id=None,
        action=action,
        actor=user.user_id,
        status_from=previous["role"] if previous is not None else None,
        status_to=role,
        metadata={
            "target_user_id": user_id,
            "old_branch": previous_branch,
            "new_branch": branch,
            "old_active": bool(previous["is_active"]) if previous is not None else None,
            "new_active": is_active,
        },
        branch=branch or previous_branch,
    )
    db.commit()
    row = db.execute(
        text(
            """
            select user_id, email, display_name, role::text as role, branch, is_active, created_at, updated_at
            from public.user_roles where user_id = :user_id
            """
        ),
        {"user_id": user_id},
    ).mappings().one()
    return _serialize(row)


@router.post("/admin/users/{user_id}/deactivate")
def deactivate_user_role(user_id: str, db: Session = Depends(_db), user: CurrentUser = Depends(require_roles("ADMIN"))):
    row = db.execute(
        text(
            """
            update public.user_roles
            set is_active = false, updated_at = now()
            where user_id = :user_id
            returning user_id, email, display_name, role::text as role, branch, is_active, created_at, updated_at
            """
        ),
        {"user_id": user_id},
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="User role not found")
    db.commit()
    return _serialize(row)


def register_user_management_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    register_branch_master_routes(app)
    _REGISTERED = True
