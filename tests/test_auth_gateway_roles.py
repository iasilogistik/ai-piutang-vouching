from app.services.auth_gateway import _ALLOWED_LOGIN_ROLES


def test_all_application_roles_are_allowed_to_login():
    assert _ALLOWED_LOGIN_ROLES == {"ADMIN", "AUDITOR", "REVIEWER", "VIEWER"}
