from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.getenv("PRODUCTION_BASE_URL", "https://ai-piutang-vouching.vercel.app").rstrip("/")
TIMEOUT_SECONDS = float(os.getenv("SMOKE_TIMEOUT_SECONDS", "20"))

PUBLIC_UI_PATHS = (
    "/ui/users",
    "/ui/audit-findings",
    "/ui/management-actions",
    "/ui/follow-up",
    "/ui/audit-management",
    "/ui/notifications",
    "/ui/evidence-repository",
    "/ui/search",
)

PROTECTED_PATHS = (
    "/admin/users",
    "/audit-findings",
    "/management-responses",
    "/corrective-action-plans",
    "/follow-up",
    "/dashboard/audit-management",
    "/notifications",
    "/evidence-repository",
    "/search",
)


def fetch_status(path: str) -> tuple[int, str]:
    request = Request(
        f"{BASE_URL}{path}",
        headers={
            "User-Agent": "ai-piutang-vouching-production-smoke/1.0",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="replace")
            return int(response.status), body
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body


def check_equal(path: str, expected_status: int) -> None:
    try:
        status, body = fetch_status(path)
    except URLError as exc:
        raise AssertionError(f"{path}: network error: {exc}") from exc
    if status != expected_status:
        excerpt = body[:300].replace("\n", " ")
        raise AssertionError(
            f"{path}: expected HTTP {expected_status}, got {status}; body={excerpt!r}"
        )
    print(f"PASS {path} -> {status}")


def main() -> int:
    failures: list[str] = []

    try:
        status, body = fetch_status("/health")
        if status != 200:
            raise AssertionError(f"/health: expected HTTP 200, got {status}")
        payload = json.loads(body)
        if payload.get("status") != "healthy":
            raise AssertionError(f"/health: expected status=healthy, got {payload!r}")
        print("PASS /health -> 200 healthy")
    except (AssertionError, URLError, json.JSONDecodeError) as exc:
        failures.append(str(exc))

    for path in PUBLIC_UI_PATHS:
        try:
            check_equal(path, 200)
        except AssertionError as exc:
            failures.append(str(exc))

    for path in PROTECTED_PATHS:
        try:
            check_equal(path, 401)
        except AssertionError as exc:
            failures.append(str(exc))

    if failures:
        print("\nPRODUCTION SMOKE FAILED", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"\nPRODUCTION SMOKE PASSED for {BASE_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
