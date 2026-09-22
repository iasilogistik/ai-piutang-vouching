# TESTING REPORT

Date: 2026-09-22

## Automated validation
- GitHub CI: migration-from-head and full pytest suite are required for pull requests.
- Alembic: single migration chain through 0026_evidence_repository.
- RBAC/branch controls: regression coverage exists for user roles, navigation, branch isolation and cross-branch access denial.
- Audit workflow regression coverage includes engagement, sampling, working papers, findings, management actions, follow-up, dashboard, notifications, evidence repository and global search/export.
- Release readiness coverage includes health compatibility, database connectivity, schema parity and non-secret release identity.
- Vercel development-branch preview deployment is disabled for routine feature/fix/chore/codex/dev branches to protect deployment quota.

## Production verification completed
The production deployment at the DEV-26 baseline was verified with:
- /health -> HTTP 200 healthy.
- Current public audit UI shells -> HTTP 200.
- Protected audit API endpoints without bearer token -> HTTP 401.
- Production Supabase migration history through 0026_evidence_repository.
- evidence_resource_links table present with RLS enabled and policies applied.

## Supabase security advisor
One open warning remains:
- auth_leaked_password_protection — leaked-password protection is disabled.

Tracked separately as SEC-01. The current connector can inspect this advisor but does not expose an authorized Auth configuration write action.

## Remaining UAT
- Real handwriting/signature/stamp accuracy across representative documents.
- Authenticated browser UAT using representative ADMIN/AUDITOR/REVIEWER/VIEWER users.
- Multi-branch end-to-end UAT including evidence, findings, follow-up and closing.
- Final release smoke on the latest production SHA after Vercel quota/rate-limit recovery when required.
