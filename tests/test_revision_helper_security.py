import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.services.release_readiness import EXPECTED_SCHEMA_REVISION


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "0031_revision_helper_acl.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("revision_helper_acl_0031", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_revision_helper_acl_precedes_dynamic_branch_scope():
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision("0032_dynamic_branch_scope")
    assert revision.down_revision == "0031_revision_helper_acl"
    assert EXPECTED_SCHEMA_REVISION == "0032_dynamic_branch_scope"


def test_revision_helper_acl_revokes_browser_roles(monkeypatch):
    module = _load_migration()
    executed = []
    monkeypatch.setattr(module, "_function_exists", lambda: True)
    monkeypatch.setattr(module.op, "execute", executed.append)

    module.upgrade()

    sql = "\n".join(str(item).lower() for item in executed)
    assert "from anon" in sql
    assert "from authenticated" in sql
    assert "from public" in sql
    assert "to postgres, authenticator, service_role" in sql
    assert "grant execute" in sql


def test_revision_helper_acl_role_sets_are_narrow():
    module = _load_migration()
    assert module.ALLOWED_EXECUTE_ROLES == ("postgres", "authenticator", "service_role")
    assert set(module.REVOKED_EXECUTE_ROLES) == {"public", "anon", "authenticated"}
    assert "anon" not in module.ALLOWED_EXECUTE_ROLES
    assert "authenticated" not in module.ALLOWED_EXECUTE_ROLES
