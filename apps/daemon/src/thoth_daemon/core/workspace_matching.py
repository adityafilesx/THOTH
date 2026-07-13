"""Authoritative foreground-to-workspace association.

Approved paths and the active task's workspace id are authority. Window
titles, aliases, and bundle ids are hints only and can never grant scope.
Matching is snapshot-based, symlink-safe, and returns no raw path evidence.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from thoth_daemon.security.paths import expand_and_resolve, is_denied_path


class WorkspaceAssociationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(min_length=1)
    approved_root_path: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    app_bundle_ids: tuple[str, ...] = ()
    title_hints: tuple[str, ...] = ()
    approved: bool = False
    verified_at: datetime
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _valid_window(self) -> WorkspaceAssociationProfile:
        if self.expires_at is not None and self.expires_at <= self.verified_at:
            raise ValueError("workspace profile expiry must follow verification")
        return self


class WorkspaceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    active_bundle_id: str | None = None
    redacted_window_title: str | None = None
    approved_workspace_path: str | None = None
    task_workspace_id: str | None = None
    recent_artifact_path: str | None = None
    terminal_working_directory: str | None = None
    finder_path: str | None = None


class WorkspaceMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str
    authoritative_sources: tuple[str, ...]
    hint_sources: tuple[str, ...]


class AmbiguousWorkspaceMatch(Exception):
    def __init__(self, workspace_ids: tuple[str, ...]) -> None:
        self.workspace_ids = workspace_ids
        super().__init__(f"multiple approved workspaces match: {', '.join(workspace_ids)}")


def _fold(value: str) -> str:
    return value.strip().casefold()


def _path_within(candidate: str, root: str) -> bool:
    resolved_candidate = expand_and_resolve(candidate)
    resolved_root = expand_and_resolve(root)
    candidate_folded = str(resolved_candidate).casefold()
    root_folded = str(resolved_root).casefold().rstrip("/")
    return candidate_folded == root_folded or candidate_folded.startswith(root_folded + "/")


class WorkspaceMatcher:
    def __init__(self, profiles: list[WorkspaceAssociationProfile]) -> None:
        self._profiles = tuple(profiles)

    def match(self, evidence: WorkspaceEvidence, now: datetime) -> WorkspaceMatch | None:
        matches: list[WorkspaceMatch] = []
        path_evidence = (
            ("approved_workspace_path", evidence.approved_workspace_path),
            ("recent_artifact_path", evidence.recent_artifact_path),
            ("terminal_working_directory", evidence.terminal_working_directory),
            ("finder_path", evidence.finder_path),
        )

        for profile in self._profiles:
            root = expand_and_resolve(profile.approved_root_path)
            if (
                not profile.approved
                or (profile.expires_at is not None and profile.expires_at <= now)
                or not root.is_dir()
            ):
                continue

            authority: list[str] = []
            if evidence.task_workspace_id and _fold(evidence.task_workspace_id) == _fold(
                profile.workspace_id
            ):
                authority.append("task_workspace_id")
            for source, candidate in path_evidence:
                if candidate and _path_within(candidate, profile.approved_root_path):
                    authority.append(source)
            if not authority:
                continue

            hints: list[str] = []
            if evidence.active_bundle_id and _fold(evidence.active_bundle_id) in {
                _fold(bundle_id) for bundle_id in profile.app_bundle_ids
            }:
                hints.append("active_bundle_id")
            if evidence.redacted_window_title:
                title = _fold(evidence.redacted_window_title)
                tokens = (*profile.aliases, *profile.title_hints)
                if any(_fold(token) in title for token in tokens if token.strip()):
                    hints.append("redacted_window_title")

            matches.append(
                WorkspaceMatch(
                    workspace_id=profile.workspace_id,
                    authoritative_sources=tuple(authority),
                    hint_sources=tuple(hints),
                )
            )

        if len(matches) > 1:
            raise AmbiguousWorkspaceMatch(tuple(sorted(match.workspace_id for match in matches)))
        return matches[0] if matches else None


def redact_workspace_path(path: str, profile: WorkspaceAssociationProfile) -> str:
    """Return a stable, non-sensitive label suitable for logs and audits."""
    if is_denied_path(path):
        return "[redacted]"
    resolved = expand_and_resolve(path)
    root = expand_and_resolve(profile.approved_root_path)
    if not _path_within(str(resolved), str(root)):
        return "[outside-workspace]"
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        # Case-normalized matches can fail lexical relative_to on a
        # case-sensitive host. Never fall back to the raw path.
        return "[workspace]"
    return "[workspace]" if str(relative) == "." else f"[workspace]/{relative}"
