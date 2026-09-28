from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.database import engine


BUSINESS_ROOT_TABLES = (
    "documents",
    "import_batches",
    "audit_findings",
    "corrective_action_plans",
)
REQUIRED_GLOBAL_ROLES = ("AUDITOR", "REVIEWER", "VIEWER")


def _scope(branch: str | None) -> str:
    return "GLOBAL" if branch is None or not str(branch).strip() else "SCOPED"


def collect_state(connection) -> dict[str, object]:
    branches = [
        dict(row)
        for row in connection.execute(
            text(
                """
                select upper(btrim(branch)) as branch, count(*)::int as records
                from (
                    select branch from public.documents
                    union all
                    select branch from public.import_batches
                ) uploaded
                where branch is not null and btrim(branch) <> ''
                group by upper(btrim(branch))
                order by records desc, branch
                """
            )
        ).mappings()
    ]

    roles = [
        dict(row)
        for row in connection.execute(
            text(
                """
                select
                    role::text as role,
                    case
                        when branch is null or btrim(branch) = '' then 'GLOBAL'
                        else 'SCOPED'
                    end as scope,
                    nullif(upper(btrim(branch)), '') as branch,
                    count(*)::int as users
                from public.user_roles
                where coalesce(is_active, true)
                group by 1, 2, 3
                order by 1, 2, 3
                """
            )
        ).mappings()
    ]

    branchless_business: dict[str, int] = {}
    for table in BUSINESS_ROOT_TABLES:
        branchless_business[table] = int(
            connection.execute(
                text(
                    f"select count(*) from public.{table} "
                    "where branch is null or btrim(branch) = ''"
                )
            ).scalar_one()
        )

    operational_audit_trail_branchless = int(
        connection.execute(
            text(
                """
                select count(*)
                from public.audit_trail
                where (branch is null or btrim(branch) = '')
                  and entity_type <> 'USER_ROLE'
                """
            )
        ).scalar_one()
    )
    administrative_global_audit_events = int(
        connection.execute(
            text(
                """
                select count(*)
                from public.audit_trail
                where (branch is null or btrim(branch) = '')
                  and entity_type = 'USER_ROLE'
                """
            )
        ).scalar_one()
    )

    return {
        "branches": branches,
        "roles": roles,
        "branchless_business": branchless_business,
        "operational_audit_trail_branchless": operational_audit_trail_branchless,
        "administrative_global_audit_events": administrative_global_audit_events,
    }


def evaluate_state(state: dict[str, object]) -> dict[str, object]:
    issues: list[dict[str, object]] = []
    branches = {
        str(row["branch"]).upper()
        for row in state.get("branches", [])
        if row.get("branch")
    }
    roles = list(state.get("roles", []))

    def role_count(role: str, scope: str | None = None) -> int:
        return sum(
            int(row.get("users", 0))
            for row in roles
            if str(row.get("role", "")).upper() == role
            and (scope is None or str(row.get("scope", "")).upper() == scope)
        )

    if len(branches) < 2:
        issues.append(
            {
                "code": "REAL_UPLOADED_BRANCHES",
                "detail": f"Need at least 2 real uploaded branches; found {len(branches)}.",
            }
        )

    if role_count("ADMIN") < 1:
        issues.append({"code": "ADMIN_ACCOUNT", "detail": "No active ADMIN mapping."})

    for role in REQUIRED_GLOBAL_ROLES:
        if role_count(role, "GLOBAL") < 1:
            issues.append(
                {
                    "code": f"GLOBAL_{role}",
                    "detail": f"No active global {role} mapping (branch NULL/blank).",
                }
            )

    scoped_viewer_branches = {
        str(row.get("branch") or "").upper()
        for row in roles
        if str(row.get("role", "")).upper() == "VIEWER"
        and str(row.get("scope", "")).upper() == "SCOPED"
        and row.get("branch")
    }
    if not (scoped_viewer_branches & branches):
        issues.append(
            {
                "code": "SCOPED_VIEWER",
                "detail": "No active scoped VIEWER is mapped to a real uploaded UAT branch.",
            }
        )

    for table, count in dict(state.get("branchless_business", {})).items():
        if int(count) != 0:
            issues.append(
                {
                    "code": f"BRANCHLESS_{str(table).upper()}",
                    "detail": f"{table} contains {int(count)} branchless business rows.",
                }
            )

    operational = int(state.get("operational_audit_trail_branchless", 0))
    if operational:
        issues.append(
            {
                "code": "BRANCHLESS_OPERATIONAL_AUDIT",
                "detail": f"audit_trail contains {operational} branchless non-USER_ROLE events.",
            }
        )

    return {
        "ready": not issues,
        "issues": issues,
        "real_uploaded_branches": sorted(branches),
        "role_summary": roles,
        "branchless_business": state.get("branchless_business", {}),
        "operational_audit_trail_branchless": operational,
        "administrative_global_audit_events": int(
            state.get("administrative_global_audit_events", 0)
        ),
    }


def _print_human(report: dict[str, object]) -> None:
    print("UAT PREFLIGHT READY" if report["ready"] else "UAT PREFLIGHT BLOCKED")
    branches = report["real_uploaded_branches"]
    print("Real uploaded branches:", ", ".join(branches) if branches else "none")
    print("Role mappings:")
    for row in report["role_summary"]:
        branch = row.get("branch") or "ALL"
        print(
            f"- {row.get('role')} {row.get('scope')} branch={branch} users={row.get('users')}"
        )
    print("Branchless business roots:", json.dumps(report["branchless_business"], sort_keys=True))
    print(
        "Branchless operational audit events:",
        report["operational_audit_trail_branchless"],
    )
    print(
        "Branchless global USER_ROLE admin events (informational):",
        report["administrative_global_audit_events"],
    )
    if report["issues"]:
        print("Blockers:")
        for issue in report["issues"]:
            print(f"- {issue['code']}: {issue['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only live UAT prerequisite checker.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    try:
        with engine.connect() as connection:
            state = collect_state(connection)
    except Exception as exc:
        print(f"UAT PREFLIGHT ERROR: {exc}", file=sys.stderr)
        return 1

    report = evaluate_state(state)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
