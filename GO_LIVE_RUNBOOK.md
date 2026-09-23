# GO-LIVE RUNBOOK — AI Piutang Vouching

## Tujuan

Runbook ini menjadi SOP rilis production dan handover aplikasi.

## A. Release freeze

Sebelum final release:
1. Tetapkan candidate SHA di `main`.
2. Tidak menambah fitur baru selama acceptance final.
3. Pastikan tidak ada PR business-logic yang belum direview.
4. Catat issue blocker pada GO-LIVE #103.

## B. Database-first gate

Untuk migration additive:
1. CI wajib PASS pada `alembic upgrade head`.
2. Apply migration Supabase production.
3. Verifikasi migration history.
4. Verifikasi RLS/security/performance advisor.
5. Baru deploy application commit yang membutuhkan schema tersebut.

Jangan mengandalkan code deploy lebih dulu dari schema.

## C. Vercel release gate

Production dianggap valid hanya jika:
- deployment target = production,
- state = READY,
- `/version.commit` = SHA `main`,
- `/version.environment` = `production`.

Jika Vercel Free memberi:

```text
Deployment rate limited — retry in 24 hours.
```

jangan membuat retrigger commit berulang. Tunggu quota reset atau upgrade plan, lalu deploy latest approved `main` satu kali.

## D. Runtime smoke

Wajib cek:

```text
/health
/version
/readiness
```

Expected final:
- health: HTTP 200 + healthy,
- version: exact main SHA,
- readiness: HTTP 200 + ready + schema_current=true.

UI minimal:
- /ui/users
- /ui/audit-management
- /ui/audit-findings
- /ui/management-actions
- /ui/follow-up
- /ui/evidence-repository
- /ui/search

Semua harus HTTP 200.

Protected API tanpa token harus HTTP 401:
- /admin/users
- /audit-findings
- /management-responses
- /corrective-action-plans
- /follow-up
- /dashboard/audit-management
- /evidence-repository
- /search

Cek runtime errors setelah smoke.

## E. Database invariants

Minimal:
- documents.branch NULL = 0
- import_batches.branch NULL = 0
- audit_trail.branch NULL = 0
- audit_findings.branch NULL = 0
- corrective_action_plans.branch NULL = 0

Pastikan RLS aktif pada tabel audit/business yang relevan.

## F. Multi-role UAT

Prerequisite:
- ADMIN active,
- AUDITOR active / PASURUAN,
- REVIEWER active / PASURUAN,
- VIEWER active / PASURUAN.

Auth accounts dibuat melalui Supabase Auth resmi. Setelah itu role dipetakan melalui `/ui/users`.

Set environment token hanya pada shell lokal:

```bash
export ADMIN_TOKEN='...'
export AUDITOR_TOKEN='...'
export REVIEWER_TOKEN='...'
export VIEWER_TOKEN='...'
export UAT_BRANCH='PASURUAN'
python scripts/live_rbac_uat.py
```

Token tidak boleh masuk screenshot, issue, commit, chat, atau evidence package.

Acceptance:
- auth identity benar,
- authorized read = 200,
- admin-only gate benar,
- create/reopen/verification role gate benar,
- cross-branch request ditolak,
- seluruh matrix PASS.

## G. RLS performance consolidation

PERF-02 (#93) hanya dieksekusi setelah UAT live hijau.

Desain:
- branch-aware SELECT tetap dipertahankan,
- `FOR ALL` manage policy dipecah menjadi INSERT/UPDATE/DELETE,
- role set dan branch predicate tidak berubah,
- UAT dijalankan sebelum dan sesudah migration,
- performance advisor diulang.

## H. Auth security

SEC-01 (#79):
- Supabase organization saat ini Free.
- Leaked password protection membutuhkan Pro atau lebih tinggi.
- Pilihan go-live:
  1. upgrade plan lalu enable control, atau
  2. dokumentasikan formal risk acceptance.

Jangan membuat SQL workaround untuk hosted Auth security feature.

## I. Backup dan rollback

Sebelum migration berisiko:
- simpan backup/restore plan,
- catat current production SHA,
- catat migration head.

Rollback:
1. identifikasi previous known-good deployment,
2. rollback app,
3. untuk destructive data migration gunakan backup/restore yang disetujui, bukan blind downgrade,
4. jalankan health/version/readiness,
5. dokumentasikan reason dan impact.

## J. Evidence package

Lampirkan ke GO-LIVE #103:
- final main SHA,
- Vercel deployment ID/URL,
- health/version/readiness result,
- migration/advisor summary,
- RBAC UAT summary,
- branch-null invariant result,
- runtime error check,
- accepted risks,
- sign-off owner/date.

## K. Handover roles

### ADMIN
- user role mapping,
- branch master,
- production/release monitoring,
- issue escalation.

### AUDITOR
- engagement,
- upload/import,
- sampling,
- working paper,
- finding preparation,
- evidence linking,
- follow-up preparation.

### REVIEWER
- review queue,
- finding approval,
- management response review,
- follow-up verification,
- closing/sign-off.

### VIEWER
- authorized read-only review of audit information.

## L. Current dependencies

Track from:
- UAT-01 #89
- PERF-02 #93
- SEC-01 #79
- OPS-02 #102
- GO-LIVE #103

DEV-30 documentation is complete when this runbook and USER_GUIDE.md are reviewed and ready for handover.
