"""Scope enforcement.

A stateless decision: does an invocation's requested scope fall inside the
effective allowed scope? Paths must resolve inside an approved root and
outside the denylist; domains and apps must be explicitly granted. All inputs
are typed ResourceScope values from trusted sources (plan args + permission
store) — no free text reaches this decision (threats T1/T3)."""

from __future__ import annotations

from omnimac_daemon.schemas import ResourceScope
from omnimac_daemon.security.paths import is_denied_path, is_within


class ScopeViolation(Exception):
    def __init__(self, kind: str, value: str, reason: str) -> None:
        self.kind = kind
        self.value = value
        self.reason = reason
        super().__init__(f"scope violation ({kind}={value!r}): {reason}")


class ScopeEnforcer:
    """Pure: no state, no I/O. Raises ScopeViolation on the first offending
    target, otherwise returns None."""

    def check(self, requested: ResourceScope, allowed: ResourceScope) -> None:
        for path in requested.paths:
            self._check_path(path, allowed.paths)
        allowed_domains = {d.lower() for d in allowed.domains}
        for domain in requested.domains:
            if domain.lower() not in allowed_domains and "*" not in allowed_domains:
                raise ScopeViolation("domain", domain, "not in approved domains")
        allowed_apps = set(allowed.apps)
        for app in requested.apps:
            if app not in allowed_apps:
                raise ScopeViolation("app", app, "not in approved apps")

    @staticmethod
    def _check_path(path: str, roots: list[str]) -> None:
        if is_denied_path(path):
            raise ScopeViolation("path", path, "denied credential/system location")
        if not any(is_within(path, root) for root in roots):
            raise ScopeViolation("path", path, "outside all approved roots")
