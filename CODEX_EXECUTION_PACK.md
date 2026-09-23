# CODEX EXECUTION PACK

Version: 2.0 — 2026-09-23

## Operating mode

This file is an **execute-only instruction pack**.

Codex MUST NOT:
- analyze the architecture again;
- redesign modules;
- propose new features;
- refactor unrelated code;
- rename unrelated modules;
- change RBAC semantics;
- change branch-isolation semantics;
- expose secrets;
- create migrations unless the task explicitly says so;
- produce a new plan.

Codex MUST:
1. execute only the named task;
2. inspect only the named files plus direct dependencies needed to run tests;
3. run the specified checks;
4. self-review the diff;
5. confirm no unrelated change;
6. report PASS or BLOCKED;
7. include exact evidence;
8. stop if authorization/security equivalence cannot be proven.

The orchestration source of truth is:
- `PROJECT_COMPLETION_PLAN.md`
- GO-LIVE #103
- CODEX-01 #116

# C01 — PERF-02 Draft Final Verifier

**STATUS: PASS FINAL**

Do not repeat unless `main` changes and PR #106 is rebased with a functional diff.

Verified:
- PR #106 rebased to latest main at verification time.
- Mergeable.
- Migration CI PASS.
- Full pytest PASS: **239 passed, 51 warnings**.
- Functional diff constrained to migration/readiness/tests.
- No unrelated business-logic change.
- Authorization predicates preserved.

Current migration:
```text
0032_rls_policy_consolidation
```

If C01 must be rerun, inspect only:

```text
alembic/versions/0032_rls_policy_consolidation.py
app/services/release_readiness.py
tests/test_rls_policy_consolidation.py
tests/test_performance_hardening.py
tests/test_release_readiness.py
tests/test_revision_helper_security.py
```

Required commands:

```bash
alembic heads
alembic upgrade head
pytest -q
git diff --check
git diff main...HEAD --   alembic/versions/0032_rls_policy_consolidation.py   app/services/release_readiness.py   tests/test_rls_policy_consolidation.py   tests/test_performance_hardening.py   tests/test_release_readiness.py \
  tests/test_revision_helper_security.py
```

Return only:
- PASS/BLOCKED
- Alembic head
- pytest summary
- changed files
- authorization/security concern, if any

No architecture commentary.

# C02 — OPS-03 Production Environment Verifier

**STATUS: BLOCKED**

**External prerequisite:** authorized Vercel operator corrects Production `DATABASE_URL` to Supabase project `snmbkpjfmxrmautidlcf` and redeploys latest main.

Codex does NOT edit the environment variable.

After operator action, verify only:

```text
/version
/health
/readiness
```

Required acceptance:
- `/version.commit == latest main`
- `/version.environment == production`
- `/health == 200 healthy`
- `/readiness == 200 ready`
- `schema_current == true`

Then run authenticated schema smoke if credentials are locally available.

Also check production runtime errors.

Do not patch code unless the latest production diagnostic payload proves a code defect.

Do not request or print:
- DATABASE_URL
- database password
- access token
- service role key
- refresh token

Completion response:
- PASS/BLOCKED
- production SHA
- health status
- readiness status
- runtime-error result
- exact non-secret blocker if blocked

# C03 — Live Four-Role UAT Verifier

**STATUS: BLOCKED**

Prerequisites:
1. C02 PASS.
2. Official Supabase Auth users exist for AUDITOR, REVIEWER, VIEWER.
3. All three mapped to PASURUAN.
4. ADMIN token available locally.

Do not create users.
Do not change role mappings unless explicitly delegated by the release operator.

Run only:

```bash
export ADMIN_TOKEN='local-only'
export AUDITOR_TOKEN='local-only'
export REVIEWER_TOKEN='local-only'
export VIEWER_TOKEN='local-only'
export UAT_BRANCH='PASURUAN'
python scripts/live_rbac_uat.py
```

Never echo or persist token values.

Verify:
- identity/role
- authorized reads
- ADMIN-only denial
- AUDITOR write gate
- REVIEWER approval/verification gate
- VIEWER read-only behavior
- cross-branch denial
- search/export isolation
- evidence isolation
- follow-up/closing role gates

Completion response only:
- PASS/BLOCKED
- production SHA
- readiness state
- branch
- role matrix PASS/FAIL
- failed route names, if any
- security concern, if any

# C04 — Post-0032 Authorization Equivalence

**STATUS: BLOCKED**

Prerequisites:
- C03 PASS recorded.
- Development/Release operator applies `0032_rls_policy_consolidation` schema-first.
- Production application/release contract points to 0032.

Codex does NOT redesign policy logic.

Run the exact same C03 UAT matrix.

Compare PRE vs POST.

Required acceptance:
- every authorization outcome identical;
- cross-branch denial intact;
- no new role escalation;
- targeted multiple-permissive-policy warnings reduced/removed;
- no new security advisor issue caused by 0032.

If PRE != POST:
- return BLOCKED;
- list exact route/action difference;
- do not weaken policy to make tests pass.

Completion response:
- PASS/BLOCKED
- PRE/POST matrix comparison
- advisor delta
- changed authorization outcome, if any

# C05 — Final Repository / Release Verifier

**STATUS: BLOCKED**

Prerequisites:
- C02 PASS
- C03 PASS
- C04 PASS
- SEC-01 disposition recorded
- all required PRs merged

Run:

```bash
alembic heads
alembic upgrade head
pytest -q
git status --short
git diff --check
```

Verify:
- exactly one Alembic head;
- release readiness expected revision equals Alembic head;
- no required implementation PR left open;
- final production SHA equals final main;
- `/health` green;
- `/readiness` green;
- documentation present;
- no accidental secret files;
- `vercel.json` deployment governance still present.

Required files:

```text
USER_GUIDE.md
GO_LIVE_RUNBOOK.md
HANDOVER_CHECKLIST.md
PROJECT_COMPLETION_PLAN.md
CODEX_EXECUTION_PACK.md
UAT_MULTI_ROLE.md
DEPLOYMENT.md
PROJECT_STATUS.md
TESTING_REPORT.md
```

Completion response only:
- PASS/BLOCKED
- Alembic head
- pytest summary
- production SHA
- readiness result
- missing files
- remaining blocker issue numbers

# CODEX SELF-CHECK — mandatory for every task

Before reporting PASS, Codex must complete all of these:

```text
[ ] Requested scope complete
[ ] Required commands executed
[ ] Tests pass
[ ] git diff --check passes
[ ] Diff self-reviewed
[ ] No unrelated file change
[ ] No secret introduced
[ ] No RBAC/branch semantic broadening
[ ] No unresolved security concern
[ ] Evidence recorded
```

If any box cannot be checked, return BLOCKED.

# Completion format

Codex response must be concise and contain only:

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
