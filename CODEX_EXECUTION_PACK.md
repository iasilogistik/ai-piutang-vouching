# CODEX EXECUTION PACK

Version: 3.2 — 2026-09-24

## Execute-only mode

Codex MUST NOT:
- analyze architecture again;
- redesign modules;
- propose new features;
- refactor unrelated code;
- change RBAC semantics;
- change branch-isolation semantics;
- expose secrets;
- create migrations unless the named task explicitly requires it;
- output a new plan.

Codex MUST:
1. execute only the named task;
2. inspect only named files and direct test dependencies;
3. run required checks;
4. self-review the diff;
5. confirm no unrelated change;
6. report PASS or BLOCKED;
7. record exact evidence;
8. stop if security/authorization equivalence cannot be proven.

Sources of truth:
- `PROJECT_COMPLETION_PLAN.md`
- GO-LIVE #103
- CODEX-01 #116

# C01 — PERF-02 Draft Final Verifier
**STATUS: PASS FINAL**

Latest-baseline evidence:
- last C01 functional baseline remains PASS FINAL; rerun only after PR #106 functional rebase/diff
- PR #106 base: same SHA
- PR #106 head: `e72ebdb456b0ea2c00dd2c07c3e33c1bc9d410a6`
- draft: true
- mergeable: true
- CI: PASS
- migration: `0032_rls_policy_consolidation`
- no application business-logic module changed

Do not rerun C01 unless PR #106 receives a functional diff or is rebased after a new main change.

If rerun is required, inspect only:
```text
alembic/versions/0032_rls_policy_consolidation.py
app/services/release_readiness.py
tests/test_rls_policy_consolidation.py
tests/test_performance_hardening.py
tests/test_release_readiness.py
tests/test_revision_helper_security.py
```

Run:
```bash
alembic heads
alembic upgrade head
pytest -q
git diff --check
```

# C02 — OPS-03 Production Environment Verifier
**STATUS: BLOCKED — external operator action only**

BUG-05 development hotfix is complete and MUST NOT be re-analyzed:
- PR #121 merged
- CI PASS
- production main: `368e52c9068069c58d9074e372239c6178338708`
- `/version`: 200 and exact main SHA
- application import succeeds
- public UI shells: 200
- protected APIs without token: 401

Remaining external prerequisite:
- authorized Vercel operator replaces Production `DATABASE_URL` with the exact Supabase **Connect → Transaction pooler** string for project `snmbkpjfmxrmautidlcf`
- redeploy latest main exactly once

Current blocker evidence:
- `/health`: 500
- `/readiness`: 503 `database_unavailable`
- runtime reaches shared pooler port 6543
- database authentication fails for user `postgres`

Codex does not edit, request, print, or reconstruct the env value.
Codex performs no architecture analysis and no code patch unless the post-operator evidence proves a new application defect.

Verify only:
- /version
- /health
- /readiness
- production runtime errors
- authenticated schema smoke only if local credentials already exist

PASS:
- version commit == latest main
- environment == production
- health 200 healthy
- readiness 200 ready
- schema_current true
- no release-caused runtime errors

# C03 — Live Four-Role UAT Verifier
**STATUS: BLOCKED — requires C02 + complete four-role Auth/mapping set**

Prerequisites:
- C02 PASS
- four effective sessions: ADMIN / AUDITOR / REVIEWER / VIEWER
- AUDITOR/REVIEWER/VIEWER mapped to PASURUAN
- current aggregate production state is only 3 Auth users and 0 active `public.user_roles`, so C03 is not ready
- ADMIN session available locally

Run only:
```bash
export ADMIN_TOKEN='local-only'
export AUDITOR_TOKEN='local-only'
export REVIEWER_TOKEN='local-only'
export VIEWER_TOKEN='local-only'
export UAT_BRANCH='PASURUAN'
python scripts/live_rbac_uat.py
```

Never echo/persist tokens.

Verify:
- identity/role
- authorized reads
- admin-only denial
- auditor write gate
- reviewer approval/verification
- viewer read-only
- cross-branch denial
- search/export isolation
- evidence isolation
- follow-up/closing gates

# C04 — Post-0032 Authorization Equivalence
**STATUS: BLOCKED — requires C03 PASS + schema-first 0032**

Run the exact C03 matrix after 0032.

PASS:
- PRE == POST for every authorization outcome
- cross-branch denial intact
- no role escalation
- target permissive-policy warnings reduced/removed
- no new security advisor issue caused by 0032

If PRE != POST:
- return BLOCKED
- list exact difference
- do not weaken RLS

# C05 — Final Repository / Release Verifier
**STATUS: BLOCKED**

Prerequisites:
- C02 PASS
- C03 PASS
- C04 PASS
- SEC-01 disposition recorded
- required PRs merged

Run:
```bash
alembic heads
alembic upgrade head
pytest -q
git status --short
git diff --check
```

Verify:
- one Alembic head
- readiness expected revision == Alembic head
- production SHA == final main
- health/readiness green
- required docs present
- no secret files
- deployment governance present
- no required implementation PR left open

# Mandatory self-check

Before PASS:
```text
[ ] Requested scope complete
[ ] Required commands/checks executed
[ ] Tests pass
[ ] git diff --check passes
[ ] Diff self-reviewed
[ ] No unrelated change
[ ] No secret introduced
[ ] No RBAC/branch semantic broadening
[ ] No unresolved security concern
[ ] Evidence recorded
```

If any box cannot be checked: return BLOCKED.

# Completion format

```text
STATUS: PASS | BLOCKED
TASK: C0X
EVIDENCE:
- ...
CHANGED FILES:
- ...
BLOCKER:
- none | exact blocker
SECURITY/AUTHORIZATION:
- none | exact concern
```

Do not output repository history.
Do not output a new plan.
Do not suggest architecture changes.
