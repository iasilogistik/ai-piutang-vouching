from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = os.getenv("UAT_BASE_URL", "https://ai-piutang-vouching.vercel.app").rstrip("/")
UAT_BRANCH = os.getenv("UAT_BRANCH", "").strip().upper()
UAT_SECOND_BRANCH = os.getenv("UAT_SECOND_BRANCH", "").strip().upper()
SCOPED_VIEWER_BRANCH = os.getenv("SCOPED_VIEWER_BRANCH", "").strip().upper()
TIMEOUT_SECONDS = float(os.getenv("UAT_TIMEOUT_SECONDS", "20"))
MISSING_ID = 2_147_483_647

ROLES = ("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")
GLOBAL_BRANCH_ROLES = ("AUDITOR", "REVIEWER", "VIEWER")


@dataclass(frozen=True)
class CheckResult:
    role: str
    name: str
    expected: int
    actual: int
    passed: bool


def _tokens_from_env() -> dict[str, str]:
    tokens: dict[str, str] = {}
    missing: list[str] = []
    for role in ROLES:
        name = f"{role}_TOKEN"
        value = os.getenv(name, "").strip()
        if not value:
            missing.append(name)
        else:
            tokens[role] = value

    scoped_name = "SCOPED_VIEWER_TOKEN"
    scoped_value = os.getenv(scoped_name, "").strip()
    if not scoped_value:
        missing.append(scoped_name)
    else:
        tokens["SCOPED_VIEWER"] = scoped_value

    for name, value in (
        ("UAT_BRANCH", UAT_BRANCH),
        ("UAT_SECOND_BRANCH", UAT_SECOND_BRANCH),
        ("SCOPED_VIEWER_BRANCH", SCOPED_VIEWER_BRANCH),
    ):
        if not value:
            missing.append(name)

    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    if UAT_BRANCH == UAT_SECOND_BRANCH:
        raise RuntimeError("UAT_SECOND_BRANCH must differ from UAT_BRANCH")
    if SCOPED_VIEWER_BRANCH not in {UAT_BRANCH, UAT_SECOND_BRANCH}:
        raise RuntimeError("SCOPED_VIEWER_BRANCH must equal UAT_BRANCH or UAT_SECOND_BRANCH")
    return tokens


def _http_request(
    token: str,
    path: str,
    *,
    method: str = "GET",
    form: dict[str, object] | None = None,
) -> tuple[int, str]:
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "ai-piutang-vouching-live-rbac-uat/1.0",
    }
    if form is not None:
        data = urlencode({k: str(v) for k, v in form.items()}).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = Request(
        f"{BASE_URL}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")
    except URLError as exc:
        raise RuntimeError(f"Network error for {path}: {exc}") from exc


Transport = Callable[[str, str, str, dict[str, object] | None], tuple[int, str]]


def _expect(
    results: list[CheckResult],
    transport: Transport,
    *,
    role: str,
    token: str,
    name: str,
    path: str,
    expected: int,
    method: str = "GET",
    form: dict[str, object] | None = None,
) -> str:
    actual, body = transport(token, path, method, form)
    passed = actual == expected
    results.append(CheckResult(role, name, expected, actual, passed))
    marker = "PASS" if passed else "FAIL"
    print(f"{marker} [{role}] {name}: expected={expected} actual={actual}")
    return body


def _default_transport(
    token: str,
    path: str,
    method: str,
    form: dict[str, object] | None,
) -> tuple[int, str]:
    return _http_request(token, path, method=method, form=form)


def run_matrix(tokens: dict[str, str], transport: Transport = _default_transport) -> list[CheckResult]:
    results: list[CheckResult] = []

    # Primary UAT accounts are global across uploaded branches. ADMIN branch
    # metadata is ignored; AUDITOR/REVIEWER/VIEWER must expose branch=null.
    for role in ROLES:
        token = tokens[role]
        body = _expect(
            results,
            transport,
            role=role,
            token=token,
            name="auth identity",
            path="/auth/me",
            expected=200,
        )
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}

        actual_role = str(payload.get("role", "")).upper()
        actual_branch = payload.get("branch")
        identity_ok = actual_role == role and (
            role == "ADMIN" or actual_branch in {None, ""}
        )
        results.append(
            CheckResult(
                role=role,
                name="auth role/global-scope payload",
                expected=1,
                actual=1 if identity_ok else 0,
                passed=identity_ok,
            )
        )
        print(
            f"{'PASS' if identity_ok else 'FAIL'} [{role}] auth role/global-scope payload "
            f"(role={actual_role or '-'}, branch={actual_branch or 'ALL'})"
        )

        # Both branches must be real uploaded branches. Global roles can filter
        # and read either branch without changing their user profile.
        for branch in (UAT_BRANCH, UAT_SECOND_BRANCH):
            for path, name in (
                (f"/audit-findings?branch={branch}", f"read findings {branch}"),
                (f"/follow-up?branch={branch}", f"read follow-up {branch}"),
                (f"/search?branch={branch}&page_size=1", f"read global search {branch}"),
            ):
                _expect(
                    results,
                    transport,
                    role=role,
                    token=token,
                    name=name,
                    path=path,
                    expected=200,
                )

    _expect(
        results,
        transport,
        role="ADMIN",
        token=tokens["ADMIN"],
        name="admin user management",
        path="/admin/users",
        expected=200,
    )
    for role in GLOBAL_BRANCH_ROLES:
        _expect(
            results,
            transport,
            role=role,
            token=tokens[role],
            name="admin user management denied",
            path="/admin/users",
            expected=403,
        )

    # Dedicated scoped control account proves the optional restriction still
    # works even though the primary UAT roles are global.
    scoped_token = tokens["SCOPED_VIEWER"]
    scoped_body = _expect(
        results,
        transport,
        role="SCOPED_VIEWER",
        token=scoped_token,
        name="auth identity",
        path="/auth/me",
        expected=200,
    )
    try:
        scoped_payload = json.loads(scoped_body)
    except json.JSONDecodeError:
        scoped_payload = {}
    scoped_identity_ok = (
        str(scoped_payload.get("role", "")).upper() == "VIEWER"
        and str(scoped_payload.get("branch") or "").upper() == SCOPED_VIEWER_BRANCH
    )
    results.append(
        CheckResult(
            role="SCOPED_VIEWER",
            name="auth scoped-branch payload",
            expected=1,
            actual=1 if scoped_identity_ok else 0,
            passed=scoped_identity_ok,
        )
    )
    print(
        f"{'PASS' if scoped_identity_ok else 'FAIL'} [SCOPED_VIEWER] auth scoped-branch payload "
        f"(branch={scoped_payload.get('branch') or '-'})"
    )

    other_for_scoped = (
        UAT_SECOND_BRANCH if SCOPED_VIEWER_BRANCH == UAT_BRANCH else UAT_BRANCH
    )
    for path, name, expected in (
        (
            f"/audit-findings?branch={SCOPED_VIEWER_BRANCH}",
            "scoped findings allowed",
            200,
        ),
        (
            f"/search?branch={SCOPED_VIEWER_BRANCH}&page_size=1",
            "scoped search allowed",
            200,
        ),
        (
            f"/follow-up?branch={SCOPED_VIEWER_BRANCH}",
            "scoped follow-up allowed",
            200,
        ),
        (
            f"/audit-findings?branch={other_for_scoped}",
            "outside-scope findings denied",
            403,
        ),
        (
            f"/search?branch={other_for_scoped}&page_size=1",
            "outside-scope search denied",
            403,
        ),
        (
            f"/follow-up?branch={other_for_scoped}",
            "outside-scope follow-up denied",
            403,
        ),
    ):
        _expect(
            results,
            transport,
            role="SCOPED_VIEWER",
            token=scoped_token,
            name=name,
            path=path,
            expected=expected,
        )

    create_finding_form = {
        "engagement_id": MISSING_ID,
        "reference": "UAT-NON-MUTATING-PROBE",
        "title": "Non-mutating authorization probe",
        "severity": "LOW",
    }
    for role, expected in (
        ("ADMIN", 404),
        ("AUDITOR", 404),
        ("REVIEWER", 403),
        ("VIEWER", 403),
    ):
        _expect(
            results,
            transport,
            role=role,
            token=tokens[role],
            name="finding create role gate",
            path="/audit-findings",
            method="POST",
            form=create_finding_form,
            expected=expected,
        )

    for role, expected in (
        ("ADMIN", 404),
        ("AUDITOR", 403),
        ("REVIEWER", 404),
        ("VIEWER", 403),
    ):
        _expect(
            results,
            transport,
            role=role,
            token=tokens[role],
            name="finding reopen role gate",
            path=f"/audit-findings/{MISSING_ID}/reopen",
            method="POST",
            form={"reason": "Non-mutating UAT authorization probe"},
            expected=expected,
        )

    for role, expected in (
        ("ADMIN", 404),
        ("AUDITOR", 403),
        ("REVIEWER", 404),
        ("VIEWER", 403),
    ):
        _expect(
            results,
            transport,
            role=role,
            token=tokens[role],
            name="follow-up verification role gate",
            path=f"/corrective-action-plans/{MISSING_ID}/verification",
            method="POST",
            form={"result": "VERIFIED", "note": "Non-mutating UAT authorization probe"},
            expected=expected,
        )

    return results


def main() -> int:
    try:
        tokens = _tokens_from_env()
        results = run_matrix(tokens)
    except RuntimeError as exc:
        print(f"UAT PRECONDITION FAILED: {exc}", file=sys.stderr)
        return 2

    failed = [x for x in results if not x.passed]
    print(f"\nRBAC UAT summary: {len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("Failed checks:", file=sys.stderr)
        for item in failed:
            print(
                f"- [{item.role}] {item.name}: expected={item.expected} actual={item.actual}",
                file=sys.stderr,
            )
        return 1

    print("LIVE RBAC UAT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
