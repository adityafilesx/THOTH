import pytest
from pydantic import ValidationError

from thoth_daemon.schemas import PermissionGrant
from thoth_daemon.storage.models import Base


def test_permission_grant_defaults() -> None:
    g = PermissionGrant(workspace_id="w1", kind="path", value="~/projects/thoth")
    assert g.revoked is False and g.id


def test_permission_grant_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        PermissionGrant(workspace_id="w1", kind="network", value="x")  # type: ignore[arg-type]


def test_permission_grant_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        PermissionGrant(workspace_id="w1", kind="path", value="x", foo=1)  # type: ignore[call-arg]


def test_new_tables_registered() -> None:
    assert "workspace_profiles" in Base.metadata.tables
    assert "permission_grants" in Base.metadata.tables
