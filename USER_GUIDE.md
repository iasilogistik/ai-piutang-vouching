# USER GUIDE — AI Piutang Vouching

Dokumen ini adalah panduan penggunaan aplikasi untuk tim Internal Audit.

## 1. Akses dan login

Production:

```text
https://ai-piutang-vouching.vercel.app
```

Gunakan akun Supabase Auth resmi. Setelah login, aplikasi membaca role dari `public.user_roles`.

Role yang didukung:
- **ADMIN** — akses lintas cabang, user/branch management, seluruh workflow.
- **AUDITOR** — menjalankan pekerjaan audit pada cabang yang ditetapkan.
- **REVIEWER** — review, approval, verification, dan closing sesuai workflow.
- **VIEWER** — read-only sesuai cabang yang ditetapkan.

Non-ADMIN wajib memiliki branch aktif. Branch isolation berlaku di application layer dan RLS database pada tabel yang relevan.

## 2. Navigasi utama

### ADMIN
Dashboard, Audit Management, Engagements, Sampling, Working Papers, Findings, Management Actions, Follow-up, Evidence Repository, Upload, Vouching, Workflow, Control Evidence, Exceptions, Review Queue, Audit Trail, Reports, Closing, Users, Branches.

### AUDITOR
Semua aktivitas audit operasional kecuali administrasi user/branch dan kewenangan final reviewer/admin tertentu.

### REVIEWER
Review queue, findings, working papers, management actions, follow-up verification, reports, dan closing. Reviewer tidak digunakan sebagai pengganti auditor untuk aktivitas input yang dibatasi role.

### VIEWER
Akses baca pada dashboard, engagement, sampling, working papers, findings, management actions, follow-up, evidence repository, workflow, reports, dan evidence sesuai cabang.

## 3. Alur audit yang direkomendasikan

### A. Buat Audit Engagement
Buka:

```text
/ui/audit-engagements
```

Isi kode engagement, judul, periode, cabang, auditor, dan reviewer. Gunakan engagement sebagai induk untuk sampling, working paper, finding, dan proses penutupan.

### B. Import population / dokumen
Buka:

```text
/ui/upload
```

Gunakan untuk:
- import data SAP/population,
- upload Billing,
- upload SPJ,
- memicu extraction/OCR dan control-evidence processing.

Pastikan cabang yang dipilih benar sebelum upload.

### C. Vouching dan reconciliation
Buka:

```text
/ui/uat-pasuruan
/ui/control-evidence
```

Review:
- SAP vs Billing,
- Billing vs SPJ,
- nominal,
- nomor dokumen,
- partial payment,
- tanda tangan/evidence,
- stempel dan nama stempel,
- alasan manual review.

Sistem tidak menyatakan tanda tangan/stempel asli. Sistem hanya mendeteksi evidence, membaca informasi bila memungkinkan, dan mengarahkan kondisi ambigu ke REVIEW.

### D. Sampling
Buka:

```text
/ui/audit-sampling
```

Hubungkan population ke engagement, pilih metode sampling, dan dokumentasikan sample yang diuji. Jangan mengubah source population untuk menyesuaikan hasil sample.

### E. Working Paper
Buka:

```text
/ui/audit-working-papers
```

Dokumentasikan:
- audit objective,
- procedure performed,
- result/observation,
- conclusion,
- evidence links,
- exceptions.

Working paper yang sudah direview hanya dapat diubah melalui controlled transition/reopen yang tersedia.

### F. Audit Findings
Buka:

```text
/ui/audit-findings
```

Finding formal menggunakan struktur:
- Condition,
- Criteria,
- Cause,
- Effect/Risk,
- Recommendation.

Severity:
- LOW
- MEDIUM
- HIGH
- CRITICAL

Lifecycle:

```text
DRAFT -> IN_REVIEW -> APPROVED -> ISSUED
```

Finding APPROVED/ISSUED tidak diedit diam-diam. Gunakan reopen dengan reason jika perubahan diperlukan.

### G. Management Response dan Corrective Action Plan
Buka:

```text
/ui/management-actions
```

Management response hanya dibuat untuk finding yang sudah ISSUED.

Position:
- AGREE
- PARTIAL
- DISAGREE

Response lifecycle:

```text
DRAFT -> SUBMITTED -> ACCEPTED / RETURNED
```

Setelah response ACCEPTED, buat Corrective Action Plan dengan:
- action description,
- PIC,
- target date,
- completion notes.

### H. Follow-up
Buka:

```text
/ui/follow-up
```

Pantau progress, due date, overdue, evidence completion, submission for verification, reviewer verification, closing, dan reopening.

Reviewer/Admin melakukan verification sesuai kewenangan workflow.

### I. Evidence Repository
Buka:

```text
/ui/evidence-repository
```

Gunakan untuk mencari evidence yang terhubung dengan:
- engagement,
- working paper,
- finding,
- corrective action,
- dokumen audit lainnya.

Jangan mengganti source evidence hanya untuk mengubah hasil audit. Gunakan version/history dan link yang tersedia.

### J. Search
Buka:

```text
/ui/search
```

Search mengikuti hak akses user dan branch. Gunakan untuk mencari objek audit lintas modul tanpa melewati RBAC.

### K. Reports dan Closing
Buka:

```text
/ui/audit-reports
/ui/audit-closing
```

Pastikan review dan evidence sudah memadai sebelum membuat report snapshot/export atau menutup engagement.

Closing mengikuti role gate auditor/reviewer/admin dan terekam di audit trail.

## 4. User dan branch administration

### User
ADMIN membuka:

```text
/ui/users
```

Halaman ini **tidak membuat Supabase Auth account**. User Auth harus sudah dibuat melalui jalur Supabase Auth resmi. Setelah user ID tersedia, ADMIN memetakan:
- user ID,
- email/display name,
- role,
- branch,
- active/inactive.

### Branch
ADMIN membuka:

```text
/ui/branches
```

Gunakan canonical branch master. Non-ADMIN harus menggunakan branch aktif.

## 5. Audit Trail dan Notifications

Audit trail:

```text
/ui/audit-trail
```

Gunakan untuk menelusuri actor, action, status transition, branch, dan metadata audit.

Notifications:

```text
/ui/notifications
```

Gunakan untuk reminder/action item yang dihasilkan sistem.

## 6. Aturan penggunaan penting

1. Jangan membagikan bearer token, password, refresh token, database credential, atau service key.
2. Jangan memasukkan user langsung ke `auth.users` melalui SQL.
3. Jangan mengubah branch user untuk melewati branch isolation.
4. Jangan menandai REVIEW menjadi PASS tanpa evidence/reason yang memadai.
5. AI/OCR membantu extraction dan detection; keputusan audit tetap pada auditor/reviewer.
6. Finding dan working paper yang sudah formal/reviewed harus diubah melalui controlled transition.
7. Gunakan Audit Trail untuk setiap investigasi atas perubahan status penting.

## 7. Jika halaman tidak bekerja

Urutan pengecekan:
1. `/health` harus 200 healthy.
2. `/version` harus menunjukkan commit production yang diharapkan.
3. `/readiness` harus 200 ready untuk release final.
4. Pastikan token belum expired.
5. Pastikan role/branch mapping masih aktif.
6. Jika masalah tetap terjadi, catat route, waktu, role, branch, dan error message tanpa menyalin credential.

## 8. UAT wajib sebelum go-live penuh

Live multi-role UAT menggunakan:
- ADMIN
- AUDITOR / PASURUAN
- REVIEWER / PASURUAN
- VIEWER / PASURUAN

Runbook teknis:

```text
UAT_MULTI_ROLE.md
scripts/live_rbac_uat.py
```

Go-live penuh hanya dilakukan setelah gate di issue #103 selesai atau risiko residual diterima secara eksplisit oleh project owner.
