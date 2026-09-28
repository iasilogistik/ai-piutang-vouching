# CODEX EXECUTION PACK

Version: 4.0 — 2026-09-25

## Operating mode

This is an **execute-only** instruction pack. Architecture is locked by issue #128 and `FINAL_DEVELOPMENT_PLAN.md`.

Codex MUST NOT:
- re-analyze or redesign architecture;
- propose a different branch model;
- restore PASURUAN or any branch as a global default;
- redesign roles/RBAC;
- weaken RLS to make tests pass;
- add row-level multi-branch SAP behavior unless a new issue explicitly requests it;
- create Supabase Auth users or write directly to `auth.users`;
- expose or commit tokens, passwords, service keys, database URLs, or secrets;
- refactor unrelated code.

Codex MUST:
1. execute only the assigned issue/task;
2. inspect only named files plus direct failing-test dependencies;
3. run targeted tests, migrations when applicable, and full pytest;
4. fix every failure caused by the task;
5. self-review the diff for unrelated changes;
6. verify no branch=NULL audit/business root data path is introduced;
7. report PASS or BLOCKED with exact non-secret evidence.

## Locked dynamic-branch contract

- Active user with `user_roles.branch = NULL` => global across uploaded branches.
- Non-null user branch => optional exact restriction.
- ADMIN remains global even if legacy branch metadata is populated.
- Every persisted audit/business root record still has a non-null branch.
- New upload branches auto-register in the branch catalog.
- SAP may infer one branch from Branch/Cabang/Branch Code/Kode Cabang.
- Explicit branch conflicting with inferred branch => reject.
- Multiple inferred branches in one SAP file => reject in DEV-31.
- Dynamic branch migration is `0032_dynamic_branch_scope`.
- PERF-02 RLS consolidation comes later as `0033_rls_policy_consolidation`.

# CODEX-A — DEV-31A / #129 / PR #133

Current implementation exists. Verification task only unless PR receives a new functional diff.

Verify:
- Alembic head `0032_dynamic_branch_scope`.
- `app/branch_access.py` global/restricted semantics.
- ADMIN global semantics preserved.
- 82 branch-sensitive policies converted without role-gate broadening.
- inactive/unregistered users do not gain access.
- global writes require a resolved branch.
- scoped cross-branch resource access remains denied/concealed.

Required checks:
```bash
alembic heads
alembic upgrade head
pytest -q tests/test_dynamic_branch_scope.py tests/test_branch_scope_helpers.py tests/test_branch_access.py
pytest -q
git diff --check
```

# CODEX-B — DEV-31B / #130 / PR #134

Branch: `feature/dev-31b-dynamic-branch-upload`

Do exactly:
1. Preserve `ensure_branch_catalog(...)`.
2. Preserve curated branch name/region/area on upload registration.
3. SAP aliases: Branch, Cabang, Branch Code, Kode Cabang.
4. Exactly one inferred branch per file.
5. Explicit vs inferred conflict => error.
6. Multiple inferred branches => error.
7. Billing/SPJ/Combined/Bulk/Drive typed branch => auto-register.
8. Global uploader with no inferred/supplied branch => error.
9. No branch=NULL root records.
10. Run targeted + full tests, self-review, report evidence.

Do not add row-level multi-branch SAP support.

# CODEX-C — DEV-31C / #131 / PR #135

Branch: `feature/dev-31c-dynamic-branch-ui`

Do exactly:
1. Blank branch valid for ADMIN/AUDITOR/REVIEWER/VIEWER.
2. Label blank branch exactly `Semua cabang (dinamis)`.
3. Existing branch remains optional restriction.
4. Unified Upload accepts free-form branch.
5. Combined/Bulk/Drive upload UIs also expose free-form branch.
6. Copy states new branches auto-register and SAP may infer branch.
7. Branch master is presented as a discovered catalog, not a prerequisite.
8. Remove generic PASURUAN hard-coding.
9. Run targeted + full tests, self-review, report evidence.

Do not modify RLS or migrations.

# CODEX-D — DEV-31D / #132 / PR #136

Branch: `feature/dev-31d-dynamic-branch-uat-docs`

Do exactly:
1. No default PASURUAN.
2. Require `UAT_BRANCH` and `UAT_SECOND_BRANCH`, both real uploaded branches.
3. Global AUDITOR/REVIEWER/VIEWER must read both branches.
4. Dedicated scoped VIEWER must read its branch and be denied the other.
5. Preserve admin-only, auditor-write, reviewer-reopen/verification gates.
6. Probes must remain non-mutating.
7. Never commit token values.
8. Run harness unit tests + full pytest.

# CODEX-INTEGRATION — DEV-31 combined branch

Branch: `feature/dev-31-dynamic-branch-integration`

Verify the combined result, not only lane tests:
```bash
alembic heads
alembic upgrade head
pytest -q
git diff --check
```

Also inspect:
- `app/services/branch_master.py` contains both auto-registration helper and Branch Catalog UI.
- all upload entry points send/resolve branch correctly;
- branchless user UI and backend semantics agree;
- UAT uses two real branches;
- no unrelated files changed;
- no secrets.

Return PASS only if full integration CI is green.

# CODEX-PERF — PERF-02 / #93 / PR #106

BLOCKED until live dynamic-branch UAT is PASS.

When unblocked:
1. Rebase on final dynamic-branch main.
2. Migration revision must be `0033_rls_policy_consolidation` with down revision `0032_dynamic_branch_scope`.
3. Preserve exact existing role gates and branch-scope semantics.
4. Split overlapping manage `FOR ALL` policies into INSERT/UPDATE/DELETE only.
5. Capture PRE live UAT.
6. Apply 0033 schema-first.
7. Run identical POST live UAT.
8. Require PRE == POST for all authorization outcomes.
9. Re-run Supabase security/performance advisors.
10. If any authorization differs, return BLOCKED; do not weaken RLS.

# CODEX-FINAL — repository/release verifier

Prerequisites:
- DEV-31 production release healthy;
- live dynamic UAT PASS;
- PERF-02 PRE/POST PASS;
- DEV-30 docs merged;
- SEC-01 disposition recorded;
- latest main deployed.

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
- readiness expected revision equals head;
- production `/version.commit` equals final main;
- `/health` healthy;
- `/readiness` ready;
- UI smoke 200;
- protected APIs 401 without token;
- no new runtime errors;
- handover docs present;
- no accidental secret files;
- GO-LIVE #103 evidence complete.

## Mandatory self-check before PASS

```text
[ ] Assigned scope complete
[ ] Required commands actually executed
[ ] Targeted tests PASS
[ ] Full pytest PASS
[ ] Migration chain PASS if applicable
[ ] git diff --check PASS
[ ] Diff self-reviewed
[ ] No unrelated change
[ ] No secret introduced
[ ] No branch=NULL root-data path
[ ] No RBAC/branch semantic broadening
[ ] PR updated/opened
[ ] Completion evidence posted
```

If any box cannot be checked, return BLOCKED.

## Completion format

```text
STATUS: PASS | BLOCKED
TASK: CODEX-X
EVIDENCE:
- commands/tests/result
CHANGED FILES:
- ...
MIGRATION IMPACT:
- none | exact revision
BLOCKER:
- none | exact blocker
SECURITY/AUTHORIZATION:
- unchanged | exact concern
```

Do not output a new plan. Do not repeat repository history. Do not suggest architecture changes.
