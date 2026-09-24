# CODEX EXECUTION PACK

Version: 3.0 — 2026-09-24

## Operating mode

This is an **execute-only** instruction pack.

Codex MUST NOT:
- re-analyze architecture;
- redesign modules;
- propose new features;
- refactor unrelated code;
- change RBAC semantics;
- change branch-isolation semantics;
- invent users/roles;
- weaken RLS to make tests pass;
- expose secrets;
- create a new plan.

Codex MUST:
1. execute only the named task;
2. inspect only named files and direct test dependencies;
3. run the specified checks;
4. self-review the diff;
5. confirm no unrelated change;
6. report PASS or BLOCKED;
7. include exact non-secret evidence;
8. stop if authorization/security equivalence cannot be proven.

Source of truth:
- `PROJECT_COMPLETION_PLAN.md`
- GO-LIVE #103
- CODEX-01 #116

# C01 — PERF-02 Draft Final Verifier

**STATUS: PASS FINAL**

Do not rerun unless PR #106 receives a functional diff or a rebase changes functional content.

Final verified state recorded in CODEX-01 #116:
- draft PR #106
- migration `0032_rls_policy_consolidation`
- single migration chain through 0032
- CI PASS
- full pytest PASS
- exactly 21 manage policies represented
- broad read SELECT policies untouched
- existing authorization predicates preserved
- no application business-logic module changed

If rerun is required, inspect only the files named in #116 and return PASS/BLOCKED evidence.

# C02 — Production Environment Verifier

**STATUS: PASS FINAL**

Verified on 2026-09-24:
- main: `368e52c9068069c58d9074e372239c6178338708`
- production deployment: `dpl_DnRywkE2ge7mB5qGS3gMtj9879Sh`
- `/version.commit == main`
- `/version.environment == production`
- `/health == 200 healthy`
- `/readiness == 200 ready`
- `schema_current == true`
- required production tables visible
- revision helpers return `0031_revision_helper_acl`
- latest post-deployment error/warning window clean

Do not rerun unless production SHA/database alignment changes.

# C03 — Live Four-Role UAT Verifier

**STATUS: BLOCKED**

Prerequisites:
1. C02 remains PASS.
2. Official Auth identities exist for ADMIN/AUDITOR/REVIEWER/VIEWER.
3. Application mappings are authoritative:
   - ADMIN active
   - AUDITOR -> PASURUAN active
   - REVIEWER -> PASURUAN active
   - VIEWER -> PASURUAN active
4. Tokens are available locally.

Codex MUST NOT:
- create users;
- infer role from email/name/UUID/account order;
- write to `auth.users`;
- print/store token values.

Run only:

```bash
export ADMIN_TOKEN='local-only'
export AUDITOR_TOKEN='local-only'
export REVIEWER_TOKEN='local-only'
export VIEWER_TOKEN='local-only'
export UAT_BRANCH='PASURUAN'
python scripts/live_rbac_uat.py
```

Verify only:
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

Completion response:
- PASS/BLOCKED
- production SHA
- readiness state
- branch
- role matrix PASS/FAIL
- failed route/action names if any
- security concern if any

# C04 — Post-0032 Authorization Equivalence

**STATUS: BLOCKED**

Prerequisites:
- C03 PASS recorded.
- Development/Release operator applies `0032_rls_policy_consolidation` schema-first.

Run the exact same C03 matrix.

Required acceptance:
- PRE == POST for every authorization outcome
- cross-branch denial intact
- no role escalation
- target multiple-permissive-policy warnings reduced/removed
- no new security-advisor issue caused by 0032

If PRE != POST:
- return BLOCKED
- list exact route/action difference
- do not weaken RLS

Completion response:
- PASS/BLOCKED
- PRE/POST comparison
- advisor delta
- changed authorization outcome if any

# C05 — Final Repository / Release Verifier

**STATUS: BLOCKED**

Prerequisites:
- C01 PASS
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
- exactly one Alembic head
- readiness expected revision == Alembic head
- no required implementation PR left open
- final production SHA == final main
- health green
- readiness green
- handover docs present
- no accidental secret file
- `vercel.json` governance present

Required files:
- `USER_GUIDE.md`
- `GO_LIVE_RUNBOOK.md`
- `HANDOVER_CHECKLIST.md`
- `PROJECT_COMPLETION_PLAN.md`
- `CODEX_EXECUTION_PACK.md`
- `UAT_MULTI_ROLE.md`
- `DEPLOYMENT.md`
- `PROJECT_STATUS.md`
- `TESTING_REPORT.md`

Completion response only:
- PASS/BLOCKED
- Alembic head
- pytest summary
- production SHA
- readiness
- missing files
- remaining blocker issues

# PARALLEL CODEX BOARD

```text
DONE
├─ C01 PERF-02 verifier ........ PASS FINAL
└─ C02 production verifier ..... PASS FINAL

WAITING ON DEVELOPMENT/OPERATOR
└─ C03 live four-role UAT ...... BLOCKED by authoritative mappings/sessions

AFTER C03 PASS
└─ C04 post-0032 equivalence ... BLOCKED until schema-first 0032 apply

FINAL
└─ C05 repository/release ...... BLOCKED until C03+C04+SEC-01 disposition
```

# Mandatory self-check

Before reporting PASS:

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

Do not output a new plan.
Do not repeat repository history.
Do not suggest architecture changes.
