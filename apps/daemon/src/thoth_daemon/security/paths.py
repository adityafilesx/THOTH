"""Path safety primitives for scoped filesystem and shell access.

Pure functions over paths: user-directory expansion, symlink-safe
resolution, containment checks, and an always-denied set of credential and
system locations (docs/TOOL_CONTRACTS.md §4, threat T5). No file contents
are read or written here."""

from __future__ import annotations

import os
from fnmatch import fnmatch
from pathlib import Path

# Denied even when nested inside an approved root. Anchored at the user home.
_DENY_DIR_PARTS: tuple[tuple[str, ...], ...] = (
    (".ssh",),
    (".aws",),
    (".config", "gcloud"),
    ("Library", "Keychains"),
    ("Library", "Keychain"),
)

# Denied by basename anywhere.
DENY_NAME_GLOBS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "*.pem",
    ".netrc",
)


def expand_and_resolve(path: str | Path) -> Path:
    """Expand ``~`` and ``$VARS``, then resolve to an absolute, symlink-free
    path. ``strict=False`` so a not-yet-created target resolves as far as it
    exists and the remainder is normalized lexically."""
    expanded = os.path.expanduser(os.path.expandvars(str(path)))
    return Path(expanded).resolve()


def is_within(path: str | Path, root: str | Path) -> bool:
    """True iff *path* equals *root* or is a descendant, after resolving both.
    A symlink that escapes *root* resolves outside it and returns False."""
    rp = expand_and_resolve(path)
    rr = expand_and_resolve(root)
    return rp == rr or rr in rp.parents


def is_denied_path(path: str | Path) -> bool:
    """True if *path* resolves into a credential/system location that is denied
    regardless of any grant."""
    rp = expand_and_resolve(path)
    home = Path.home().resolve()
    for parts in _DENY_DIR_PARTS:
        deny_root = home.joinpath(*parts)
        if rp == deny_root or deny_root in rp.parents:
            return True
    return any(fnmatch(rp.name, glob) for glob in DENY_NAME_GLOBS)
