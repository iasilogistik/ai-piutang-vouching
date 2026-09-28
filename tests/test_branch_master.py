from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import CurrentUser, current_user
from app.database import SessionLocal
from app.main import app
from app.services.branch_master import ensure_branch_catalog

client = TestClient(app)


def test_branch_management_ui_shell_loads():
    response = client.get("/ui/branches")
    assert response.status_code == 200
    assert "Branch Catalog" in response.text
    assert "/admin/branches" in response.text


def test_admin_can_create_normalized_update_and_deactivate_branch():
    code = " dev01-branch "
    created = client.post(
        "/admin/branches",
        data={
            "branch_code": code,
            "branch_name": "DEV 01 Branch",
            "region": "East",
            "area": "QA",
            "active": "true",
        },
    )
    assert created.status_code == 200
    assert created.json()["branch_code"] == "DEV01-BRANCH"
    assert created.json()["active"] is True

    listing = client.get("/admin/branches", params={"q": "dev01"})
    assert listing.status_code == 200
    assert any(row["branch_code"] == "DEV01-BRANCH" for row in listing.json()["branches"])

    updated = client.patch(
        "/admin/branches/DEV01-BRANCH",
        data={"branch_name": "DEV 01 Updated", "region": "JATIM"},
    )
    assert updated.status_code == 200
    assert updated.json()["branch_name"] == "DEV 01 Updated"
    assert updated.json()["region"] == "JATIM"

    deactivated = client.post("/admin/branches/DEV01-BRANCH/deactivate")
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False


def test_duplicate_branch_code_is_rejected():
    payload = {"branch_code": "DEV01-DUP", "branch_name": "Duplicate Test", "active": "true"}
    first = client.post("/admin/branches", data=payload)
    assert first.status_code == 200
    second = client.post("/admin/branches", data={**payload, "branch_code": " dev01-dup "})
    assert second.status_code == 409


def test_non_admin_cannot_modify_branch_master():
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        user_id="auditor-test", role="AUDITOR", branch="PASURUAN"
    )
    try:
        response = client.post(
            "/admin/branches",
            data={"branch_code": "DEV01-DENIED", "branch_name": "Denied"},
        )
        assert response.status_code == 403
        listing = client.get("/admin/branches")
        assert listing.status_code == 403
    finally:
        app.dependency_overrides.pop(current_user, None)



def test_upload_registration_preserves_curated_branch_metadata():
    code = "DYNAMIC-CURATED"
    created = client.post(
        "/admin/branches",
        data={
            "branch_code": code,
            "branch_name": "Curated Branch Name",
            "region": "JATIM",
            "area": "AREA-1",
            "active": "true",
        },
    )
    assert created.status_code in {200, 409}

    db = SessionLocal()
    try:
        normalized = ensure_branch_catalog(db, code.lower())
        db.commit()
        row = db.execute(
            text(
                "select branch_code, branch_name, region, area, active "
                "from public.branches where branch_code=:code"
            ),
            {"code": normalized},
        ).mappings().one()
        assert row["branch_name"] == "Curated Branch Name"
        assert row["region"] == "JATIM"
        assert row["area"] == "AREA-1"
        assert row["active"] is True
    finally:
        db.close()
