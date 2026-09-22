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
UAT_BRANCH = os.getenv("UAT_BRANCH", "PASURUAN").strip().upper()
OTHER_BRANCH = os.getenv("UAT_OTHER_BRANCH", "__UAT_OUTSIDE_SCOPE__").strip().upper()
TIMEOUT_SECONDS = float(os.getenv("UAT_TIMEOUT_SECONDS", "20"))
MISSING_ID = 2_147_483_647

ROLES = ("ADMIN", "AUDITOR", "REVIEWER", "VIEWER")


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
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
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
        expected_branch = None if role == "ADMIN" else UAT_BRANCH
        actual_branch = payload.get("branch")
        identity_ok = actual_role == role and (
            role == "ADMIN" or str(actual_branch or "").upper() == expected_branch
        )
        results.append(
            CheckResult(
                role=role,
                name="auth role/branch payload",
                expected=1,
                actual=1 if identity_ok else 0,
                passed=identity_ok,
            )
        )
        print(
            f"{'PASS' if identity_ok else 'FAIL'} [{role}] auth role/branch payload "
            f"(role={actual_role or '-'}, branch={actual_branch or '-'})"
        )

        for path, name in (
            ("/audit-findings", "read findings"),
            ("/follow-up", "read follow-up"),
            ("/search?page_size=1", "read global search"),
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
    for role in ("AUDITOR", "REVIEWER", "VIEWER"):
        _expect(
            results,
            transport,
            role=role,
            token=tokens[role],
            name="admin user management denied",
            path="/admin/users",
            expected=403,
        )

    for role in ("AUDITOR", "REVIEWER", "VIEWER"):
        for path, name in (
            (f"/audit-findings?branch={OTHER_BRANCH}", "cross-branch findings denied"),
            (f"/search?branch={OTHER_BRANCH}&page_size=1", "cross-branch search denied"),
            (f"/follow-up?branch={OTHER_BRANCH}", "cross-branch follow-up denied"),
        ):
            _expect(
                results,
                transport,
                role=role,
                token=tokens[role],
                name=name,
                path=path,
                expected=403,
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
    if OTHER_BRANCH == UAT_BRANCH:
        print("UAT_OTHER_BRANCH must differ from UAT_BRANCH", file=sys.stderr)
        return 2

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
