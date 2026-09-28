import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "0032_dynamic_branch_scope.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("dynamic_branch_0032", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dynamic_branch_scope_is_single_release_head():
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    assert ScriptDirectory.from_config(config).get_heads() == ["0032_dynamic_branch_scope"]


def test_dynamic_branch_scope_rewrites_every_branch_sensitive_policy():
    module = _load_migration()
    assert len(module._POLICIES) == 82

    transformed = []
    for _table, _policy, _command, using_expr, check_expr in module._POLICIES:
        for expression in (using_expr, check_expr):
            if expression is None:
                continue
            rewritten = module._replace_branch_scope(expression)
            assert "current_app_branch" not in rewritten
            assert "branch_scope_allows" in rewritten
            transformed.append(rewritten)

    assert transformed


def test_branch_scope_helper_requires_active_application_user():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "from public.user_roles ur" in text
    assert "coalesce(ur.is_active, true)" in text
    assert "ur.branch is null" in text
    assert "upper(trim(ur.branch)) = upper(trim(resource_branch))" in text
    assert "grant execute on function public.branch_scope_allows(text) to authenticated" in text


def test_unconverted_branch_predicate_fails_closed():
    module = _load_migration()
    bad = "x = (select current_app_branch())"
    try:
        module._replace_branch_scope(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("unconverted current_app_branch predicate must fail closed")
