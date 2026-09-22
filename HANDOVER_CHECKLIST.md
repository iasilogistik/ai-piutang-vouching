# HANDOVER CHECKLIST

Gunakan checklist ini pada saat aplikasi diserahkan ke tim operasional.

## Access
- [ ] Production URL tercatat.
- [ ] ADMIN resmi dapat login.
- [ ] AUDITOR resmi dapat login.
- [ ] REVIEWER resmi dapat login.
- [ ] VIEWER resmi dapat login.
- [ ] Non-ADMIN memiliki branch yang benar.
- [ ] Tidak ada credential di dokumen handover.

## Core workflow
- [ ] Engagement dapat dibuat/dibaca.
- [ ] Population/import dapat diproses.
- [ ] Billing/SPJ dapat di-upload.
- [ ] Reconciliation/vouching dapat dijalankan.
- [ ] Control evidence dapat direview.
- [ ] Sampling dapat ditelusuri ke engagement.
- [ ] Working paper dapat dibuat/review.
- [ ] Finding dapat melalui lifecycle sampai ISSUED.
- [ ] Management response/action plan berjalan.
- [ ] Follow-up dapat diverifikasi/closed/reopened sesuai role.
- [ ] Evidence repository dapat ditelusuri.
- [ ] Reports/export dapat dibuat.
- [ ] Closing/sign-off berjalan.
- [ ] Audit trail tersedia.

## Security and isolation
- [ ] Protected API tanpa token = 401.
- [ ] Cross-branch negative tests PASS.
- [ ] Admin-only endpoint ditolak untuk non-admin.
- [ ] Branch NULL invariant = 0 pada tabel inti.
- [ ] RLS advisor direview.
- [ ] Supabase leaked-password protection: enabled atau risk acceptance terdokumentasi.

## Production acceptance
- [ ] Production SHA = approved main.
- [ ] /health = 200 healthy.
- [ ] /version = correct SHA + production.
- [ ] /readiness = 200 ready.
- [ ] Latest UI routes = 200.
- [ ] Runtime error check bersih.
- [ ] Migration head sesuai release.

## Documentation
- [ ] USER_GUIDE.md diserahkan.
- [ ] GO_LIVE_RUNBOOK.md diserahkan.
- [ ] UAT_MULTI_ROLE.md diserahkan.
- [ ] UAT_PASURUAN_FINAL.md diserahkan.
- [ ] DEPLOYMENT.md diserahkan.

## Sign-off
- [ ] Technical owner
- [ ] Internal Audit owner
- [ ] UAT evidence attached
- [ ] Open accepted risks attached
- [ ] Go-live date recorded
