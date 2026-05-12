import pytest

from app.core.tenant import assert_local_tenant_scope, get_local_tenant_context


def test_local_tenant_context_defaults_to_configured_scope():
    context = get_local_tenant_context()

    assert context.tenant_id == "local"
    assert context.user_id is None
    assert context.is_superuser is False


def test_local_tenant_context_uses_current_user_scope(db):
    from app.models.user import User

    user = db.query(User).filter(User.username == "local-admin").one()
    context = get_local_tenant_context(user)

    assert context.tenant_id == user.tenant_id
    assert context.user_id == user.id
    assert context.is_superuser is True


def test_assert_local_tenant_scope_rejects_non_local_scope():
    assert_local_tenant_scope("local")

    with pytest.raises(ValueError, match="local tenant scope"):
        assert_local_tenant_scope("external")
