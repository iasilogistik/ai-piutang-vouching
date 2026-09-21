from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit_service import record_audit
from app.auth import CurrentUser, require_roles
from app.database import SessionLocal

router = APIRouter()
_REGISTERED = False


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def normalize_branch_code(value: str) -> str:
    code = (value or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="branch_code is required")
    if len(code) > 50:
        raise HTTPException(status_code=400, detail="branch_code must be at most 50 characters")
    return code


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _serialize(row) -> dict[str, object]:
    return {
        "id": row["id"],
        "branch_code": row["branch_code"],
        "branch_name": row["branch_name"],
        "region": row["region"],
        "area": row["area"],
        "active": bool(row["active"]),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def _get_branch(db: Session, branch_code: str):
    return db.execute(
        text("""
            select id, branch_code, branch_name, region, area, active, created_at, updated_at
            from public.branches
            where branch_code = :branch_code
        """),
        {"branch_code": normalize_branch_code(branch_code)},
    ).mappings().one_or_none()


def _branches_html() -> str:
    return """<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Branch Management - AI Piutang Vouching</title>
  <style>
    :root { --bg:#f6f8fb; --card:#fff; --line:#d9e0ea; --text:#182433; --muted:#64748b; --blue:#1f6feb; --red:#b3261e; --green:#188038; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:Arial,Helvetica,sans-serif; background:var(--bg); color:var(--text); }
    header { background:#0f172a; color:white; padding:18px 24px; }
    header h1 { margin:0; font-size:22px; }
    main { max-width:1180px; margin:0 auto; padding:20px 24px 40px; }
    .panel { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin:14px 0; }
    .grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
    label { display:block; font-size:12px; color:var(--muted); margin-bottom:5px; }
    input, select { width:100%; border:1px solid var(--line); border-radius:8px; padding:8px; font:inherit; background:white; }
    button, .button-link { border:0; border-radius:8px; padding:10px 13px; background:var(--blue); color:white; font-weight:700; cursor:pointer; text-decoration:none; display:inline-block; }
    button.secondary, .button-link.secondary { background:#475569; }
    button.danger { background:var(--red); }
    .actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
    table { width:100%; border-collapse:collapse; margin-top:10px; }
    th,td { border-bottom:1px solid var(--line); padding:8px; text-align:left; font-size:13px; }
    .ok { color:var(--green); font-weight:700; } .err { color:var(--red); font-weight:700; }
    pre { white-space:pre-wrap; word-break:break-word; background:#0f172a; color:#dbeafe; border-radius:10px; padding:12px; max-height:300px; overflow:auto; }
    @media(max-width:800px){.grid{grid-template-columns:1fr;}}
  </style>
</head>
<body>
<header><h1>Branch Management</h1><p>Master resmi cabang untuk AI Piutang Vouching.</p></header>
<main>
<section class="panel">
  <h2>Token Admin</h2>
  <label for="token">Bearer Token</label><input id="token" type="password" placeholder="Token ADMIN" />
  <div class="actions"><button id="loadBtn">Muat Cabang</button><a class="button-link secondary" href="/ui/users">User Management</a><a class="button-link secondary" href="/login">Login</a></div>
</section>
<section class="panel">
  <h2>Tambah / Edit Cabang</h2>
  <div class="grid">
    <div><label for="code">Kode Cabang</label><input id="code" placeholder="PASURUAN" /></div>
    <div><label for="name">Nama Cabang</label><input id="name" placeholder="Cabang Pasuruan" /></div>
    <div><label for="region">Region</label><input id="region" /></div>
    <div><label for="area">Area</label><input id="area" /></div>
    <div><label for="active">Status</label><select id="active"><option value="true">Aktif</option><option value="false">Nonaktif</option></select></div>
  </div>
  <div class="actions"><button id="saveBtn">Simpan</button><button class="secondary" id="resetBtn">Reset</button></div>
</section>
<section class="panel">
  <h2>Daftar Cabang</h2>
  <div class="grid"><div><label for="search">Cari</label><input id="search" placeholder="kode / nama / region / area" /></div></div>
  <table><thead><tr><th>Kode</th><th>Nama</th><th>Region</th><th>Area</th><th>Status</th><th>Aksi</th></tr></thead>
  <tbody id="rows"><tr><td colspan="6">Belum dimuat.</td></tr></tbody></table>
  <h3>Log</h3><pre id="log">Belum ada aktivitas.</pre>
</section>
</main>
<script>
const token=document.getElementById('token'); token.value=localStorage.getItem('auditToken')||'';
const rows=document.getElementById('rows'), log=document.getElementById('log');
let editing=null;
function headers(){const t=token.value.trim();if(!t)throw new Error('Bearer token ADMIN wajib diisi.');localStorage.setItem('auditToken',t);return {Authorization:`Bearer ${t}`};}
function writeLog(label,payload,ok=true){log.textContent=`[${new Date().toISOString()}] ${ok?'OK':'ERROR'} - ${label}\n${typeof payload==='string'?payload:JSON.stringify(payload,null,2)}\n\n`+(log.textContent==='Belum ada aktivitas.'?'':log.textContent);}
function setForm(b={}){editing=b.branch_code||null;document.getElementById('code').value=b.branch_code||'';document.getElementById('code').disabled=!!editing;document.getElementById('name').value=b.branch_name||'';document.getElementById('region').value=b.region||'';document.getElementById('area').value=b.area||'';document.getElementById('active').value=String(b.active!==false);}
function render(items){if(!items.length){rows.innerHTML='<tr><td colspan="6">Tidak ada cabang.</td></tr>';return;}rows.innerHTML=items.map(b=>`<tr><td>${b.branch_code}</td><td>${b.branch_name}</td><td>${b.region||'-'}</td><td>${b.area||'-'}</td><td class="${b.active?'ok':'err'}">${b.active?'Aktif':'Nonaktif'}</td><td><button class="secondary" onclick='editBranch(${JSON.stringify(b)})'>Edit</button> <button class="danger" onclick="deactivateBranch('${b.branch_code}')">Nonaktifkan</button></td></tr>`).join('');}
async function load(){try{const q=document.getElementById('search').value.trim();const r=await fetch('/admin/branches'+(q?'?q='+encodeURIComponent(q):''),{headers:headers()});const b=await r.json();if(!r.ok)throw new Error(b.detail||JSON.stringify(b));render(b.branches||[]);writeLog('Muat Cabang',b);}catch(e){writeLog('Muat Cabang',e.message,false);}}
window.editBranch=b=>setForm(b);
async function save(){try{const form=new FormData();form.append('branch_name',document.getElementById('name').value.trim());form.append('region',document.getElementById('region').value.trim());form.append('area',document.getElementById('area').value.trim());form.append('active',document.getElementById('active').value);let url='/admin/branches',method='POST';if(editing){url+='/'+encodeURIComponent(editing);method='PATCH';}else{form.append('branch_code',document.getElementById('code').value.trim());}const r=await fetch(url,{method,headers:headers(),body:form});const b=await r.json();if(!r.ok)throw new Error(b.detail||JSON.stringify(b));writeLog('Simpan Cabang',b);setForm();await load();}catch(e){writeLog('Simpan Cabang',e.message,false);}}
window.deactivateBranch=async code=>{try{const r=await fetch('/admin/branches/'+encodeURIComponent(code)+'/deactivate',{method:'POST',headers:headers()});const b=await r.json();if(!r.ok)throw new Error(b.detail||JSON.stringify(b));writeLog('Nonaktifkan Cabang',b);await load();}catch(e){writeLog('Nonaktifkan Cabang',e.message,false);}};
document.getElementById('loadBtn').onclick=load; document.getElementById('saveBtn').onclick=save; document.getElementById('resetBtn').onclick=()=>setForm(); document.getElementById('search').oninput=load;
</script>
</body>
</html>"""


@router.get("/ui/branches", response_class=HTMLResponse)
def branch_management_ui():
    return HTMLResponse(_branches_html())


@router.get("/admin/branches")
def list_branches(
    q: str | None = None,
    active: bool | None = None,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN")),
):
    clauses = []
    params: dict[str, object] = {}
    if q and q.strip():
        params["q"] = f"%{q.strip()}%"
        clauses.append("(branch_code ilike :q or branch_name ilike :q or coalesce(region, '') ilike :q or coalesce(area, '') ilike :q)")
    if active is not None:
        params["active"] = active
        clauses.append("active = :active")
    where = (" where " + " and ".join(clauses)) if clauses else ""
    rows = db.execute(
        text(f"""
            select id, branch_code, branch_name, region, area, active, created_at, updated_at
            from public.branches
            {where}
            order by active desc, branch_code
        """),
        params,
    ).mappings().all()
    return {"total": len(rows), "branches": [_serialize(row) for row in rows]}


@router.post("/admin/branches")
def create_branch(
    branch_code: str = Form(...),
    branch_name: str = Form(...),
    region: str | None = Form(None),
    area: str | None = Form(None),
    active: bool = Form(True),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN")),
):
    code = normalize_branch_code(branch_code)
    name = (branch_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="branch_name is required")
    try:
        row = db.execute(
            text("""
                insert into public.branches (branch_code, branch_name, region, area, active, updated_at)
                values (:code, :name, :region, :area, :active, now())
                returning id, branch_code, branch_name, region, area, active, created_at, updated_at
            """),
            {"code": code, "name": name, "region": _clean(region), "area": _clean(area), "active": active},
        ).mappings().one()
        record_audit(db, entity_type="BRANCH", entity_id=row["id"], action="CREATE_BRANCH", actor=user.user_id,
                     status_to="ACTIVE" if row["active"] else "INACTIVE",
                     metadata={"branch_code": code, "branch_name": name}, branch=code)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="branch_code already exists") from exc
    return _serialize(row)


@router.patch("/admin/branches/{branch_code}")
def update_branch(
    branch_code: str,
    branch_name: str | None = Form(None),
    region: str | None = Form(None),
    area: str | None = Form(None),
    active: bool | None = Form(None),
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN")),
):
    current = _get_branch(db, branch_code)
    if current is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    name = current["branch_name"] if branch_name is None else branch_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="branch_name is required")
    values = {
        "code": current["branch_code"],
        "name": name,
        "region": current["region"] if region is None else _clean(region),
        "area": current["area"] if area is None else _clean(area),
        "active": current["active"] if active is None else active,
    }
    row = db.execute(
        text("""
            update public.branches
            set branch_name=:name, region=:region, area=:area, active=:active, updated_at=now()
            where branch_code=:code
            returning id, branch_code, branch_name, region, area, active, created_at, updated_at
        """),
        values,
    ).mappings().one()
    record_audit(db, entity_type="BRANCH", entity_id=row["id"], action="UPDATE_BRANCH", actor=user.user_id,
                 status_from="ACTIVE" if current["active"] else "INACTIVE",
                 status_to="ACTIVE" if row["active"] else "INACTIVE",
                 metadata={"branch_code": row["branch_code"], "branch_name": row["branch_name"]}, branch=row["branch_code"])
    db.commit()
    return _serialize(row)


@router.post("/admin/branches/{branch_code}/deactivate")
def deactivate_branch(
    branch_code: str,
    db: Session = Depends(_db),
    user: CurrentUser = Depends(require_roles("ADMIN")),
):
    current = _get_branch(db, branch_code)
    if current is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    row = db.execute(
        text("""
            update public.branches set active=false, updated_at=now()
            where branch_code=:code
            returning id, branch_code, branch_name, region, area, active, created_at, updated_at
        """),
        {"code": current["branch_code"]},
    ).mappings().one()
    record_audit(db, entity_type="BRANCH", entity_id=row["id"], action="DEACTIVATE_BRANCH", actor=user.user_id,
                 status_from="ACTIVE" if current["active"] else "INACTIVE", status_to="INACTIVE",
                 metadata={"branch_code": row["branch_code"]}, branch=row["branch_code"])
    db.commit()
    return _serialize(row)


def register_branch_master_routes(app) -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    app.include_router(router)
    _REGISTERED = True
