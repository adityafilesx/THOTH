"""Prompt-injection boundary.

All external content (web pages, files, emails, tool output, images) is
untrusted data. It may inform a plan's *content* but can never:
change the objective, approve an action, grant permissions, expand
approved directories/domains, request credentials, disable verification,
or modify security policy.

Two mechanisms:
- ``require_trusted``: the gate every objective/approval/permission input
  must pass. Untrusted provenance raises — there is no override.
- ``scan_untrusted``: heuristic flagging of directive patterns inside
  untrusted content, for audit visibility and future model-context
  hardening. Scanning is advisory; the trust gate is the enforcement.
"""

import re

from pydantic import BaseModel, ConfigDict

from omnimac_daemon.schemas import TaggedContent

DIRECTIVE_PATTERNS: dict[str, str] = {
    "override_instructions": r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions\b",
    "role_impersonation": r"^\s*(system|assistant|developer)\s*:",
    "approval_forgery": r"\b(mark|treat|consider)?\s*(this|the)?\s*\w*\s*(as\s+)?approved\b|\bapprove\s+all\b",
    "authorization_claim": r"\bauthorized\s+to\b",
    "disable_safety": r"\bdisable\s+(verification|safety|the\s+safety\s+engine|policy)\b",
    "privileged_exec": r"\bsudo\b|\brm\s+-rf\s+/",
    "objective_override": r"\bnew\s+(objective|goal|task)\s*:",
    "permission_grant": r"\bgrant\s+(permission|access)\b|\bexpand\s+(approved|allowed)\b",
    "credential_request": r"\b(send|share|paste|exfiltrate)\b.{0,40}\b(password|credential|\.ssh|id_rsa|api[_ ]?key|token)\b",
}

_COMPILED = {name: re.compile(pattern, re.IGNORECASE | re.MULTILINE) for name, pattern in DIRECTIVE_PATTERNS.items()}


class InjectionScan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suspicious: bool
    matched_patterns: list[str]


class UntrustedContentError(Exception):
    def __init__(self, purpose: str, provenance: str) -> None:
        super().__init__(f"{provenance} content may not be used as {purpose}; only USER_TRUSTED or SYSTEM_TRUSTED provenance can cross this boundary")


def scan_untrusted(content: TaggedContent) -> InjectionScan:
    matched = [name for name, rx in _COMPILED.items() if rx.search(content.content)]
    return InjectionScan(suspicious=bool(matched), matched_patterns=matched)


def require_trusted(content: TaggedContent, purpose: str) -> TaggedContent:
    if not content.is_trusted:
        raise UntrustedContentError(purpose=purpose, provenance=content.provenance.value)
    return content
