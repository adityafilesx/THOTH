from pathlib import Path

import pytest

from omnimac_daemon.core.scope import ScopeEnforcer, ScopeViolation
from omnimac_daemon.schemas import ResourceScope


@pytest.fixture()
def enforcer() -> ScopeEnforcer:
    return ScopeEnforcer()


def _allowed(root: str) -> ResourceScope:
    return ResourceScope(paths=[root], domains=["example.com"], apps=["Safari"])


def test_in_scope_path_allowed(enforcer: ScopeEnforcer) -> None:
    root = str(Path.home() / "projects" / "omnimac")
    enforcer.check(ResourceScope(paths=[root + "/README.md"]), _allowed(root))


def test_out_of_scope_path_denied(enforcer: ScopeEnforcer) -> None:
    root = str(Path.home() / "projects" / "omnimac")
    with pytest.raises(ScopeViolation) as exc:
        enforcer.check(ResourceScope(paths=[str(Path.home() / "other" / "x.txt")]), _allowed(root))
    assert exc.value.kind == "path"


def test_denied_path_inside_root_denied(enforcer: ScopeEnforcer) -> None:
    with pytest.raises(ScopeViolation) as exc:
        enforcer.check(
            ResourceScope(paths=[str(Path.home() / ".ssh" / "id_rsa")]),
            ResourceScope(paths=[str(Path.home())]),
        )
    assert "denied" in exc.value.reason


def test_domain_allowed_and_denied(enforcer: ScopeEnforcer) -> None:
    root = str(Path.home())
    enforcer.check(ResourceScope(domains=["EXAMPLE.com"]), _allowed(root))  # case-insensitive
    with pytest.raises(ScopeViolation):
        enforcer.check(ResourceScope(domains=["evil.com"]), _allowed(root))


def test_app_allowed_and_denied(enforcer: ScopeEnforcer) -> None:
    root = str(Path.home())
    enforcer.check(ResourceScope(apps=["Safari"]), _allowed(root))
    with pytest.raises(ScopeViolation):
        enforcer.check(ResourceScope(apps=["Terminal"]), _allowed(root))


def test_empty_requested_scope_always_allowed(enforcer: ScopeEnforcer) -> None:
    enforcer.check(ResourceScope(), ResourceScope())
