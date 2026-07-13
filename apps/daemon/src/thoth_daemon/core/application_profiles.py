"""Versioned, authoritative application capability profiles.

Profiles are static trusted data. Model output and application/web content may
request a capability, but can neither add one nor change its classification.
Unknown, forbidden, and non-opted-in experimental capabilities fail closed.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from thoth_daemon.core.focus import FocusPolicy


class CapabilityStatus(StrEnum):
    VERIFIED = "verified"
    EXPERIMENTAL = "experimental"
    FORBIDDEN = "forbidden"


class InterfaceKind(StrEnum):
    NATIVE_API = "native_api"
    BROWSER_DOM = "browser_dom"
    CLI = "cli"
    URL_SCHEME = "url_scheme"
    ACCESSIBILITY = "accessibility"


class ProfileVerifier(StrEnum):
    NSWORKSPACE_RUNNING = "nsworkspace_running"
    NSWORKSPACE_FOREGROUND = "nsworkspace_foreground"
    BROWSER_URL = "browser_url"
    FILE_EXISTS = "file_exists"
    ACCESSIBILITY_VALUE = "accessibility_value"
    WORKSPACE_ASSOCIATION = "workspace_association"


class ApplicationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]+$")
    display_name: str = Field(min_length=1)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    required_permissions: tuple[str, ...]
    verified_capabilities: tuple[str, ...]
    experimental_capabilities: tuple[str, ...]
    forbidden_operations: tuple[str, ...]
    preferred_interface_order: tuple[InterfaceKind, ...] = Field(min_length=1)
    verifier_mapping: dict[str, ProfileVerifier]
    default_focus_behaviour: FocusPolicy
    last_real_verification_date: date | None

    @property
    def version_tuple(self) -> tuple[int, int, int]:
        major, minor, patch = self.version.split(".")
        return int(major), int(minor), int(patch)

    @model_validator(mode="after")
    def _validate_capabilities(self) -> ApplicationProfile:
        groups = (
            set(self.verified_capabilities),
            set(self.experimental_capabilities),
            set(self.forbidden_operations),
        )
        if any(
            len(values) != len(original)
            for values, original in zip(
                groups,
                (
                    self.verified_capabilities,
                    self.experimental_capabilities,
                    self.forbidden_operations,
                ),
                strict=True,
            )
        ):
            raise ValueError("capability lists must not contain duplicates")
        if groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2]:
            raise ValueError("a capability may have only one authoritative status")
        declared = groups[0] | groups[1]
        unknown_verifiers = set(self.verifier_mapping) - declared
        if unknown_verifiers:
            raise ValueError(
                f"verifier mapping references undeclared capabilities: {unknown_verifiers}"
            )
        missing = groups[0] - set(self.verifier_mapping)
        if missing:
            raise ValueError(f"verified capabilities require verifier mappings: {missing}")
        if groups[0] and self.last_real_verification_date is None:
            raise ValueError("verified capabilities require a real verification date")
        return self


class CapabilityAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_id: str
    capability: str
    status: CapabilityStatus
    verifier: ProfileVerifier | None = None


class ApplicationProfileError(Exception):
    pass


class UnknownApplication(ApplicationProfileError):
    pass


class DuplicateApplicationProfile(ApplicationProfileError):
    pass


class CapabilityForbidden(ApplicationProfileError):
    pass


class CapabilityUnavailable(ApplicationProfileError):
    pass


class ApplicationProfileRegistry:
    def __init__(self, profiles: list[ApplicationProfile]) -> None:
        self._profiles: dict[str, ApplicationProfile] = {}
        for profile in profiles:
            if profile.bundle_id in self._profiles:
                raise DuplicateApplicationProfile(
                    f"duplicate application profile for {profile.bundle_id!r}"
                )
            self._profiles[profile.bundle_id] = profile

    def all(self) -> tuple[ApplicationProfile, ...]:
        return tuple(self._profiles.values())

    def get(self, bundle_id: str) -> ApplicationProfile:
        profile = self._profiles.get(bundle_id)
        if profile is None:
            raise UnknownApplication(f"unknown application {bundle_id!r}")
        return profile

    def authorize(
        self,
        bundle_id: str,
        capability: str,
        *,
        allow_experimental: bool = False,
        model_requested_status: str | None = None,
    ) -> CapabilityAuthorization:
        """Resolve against trusted profile data; model status is intentionally ignored."""
        del model_requested_status
        profile = self.get(bundle_id)
        if capability in profile.forbidden_operations:
            raise CapabilityForbidden(f"{capability!r} is forbidden for {profile.display_name}")
        if capability in profile.verified_capabilities:
            return CapabilityAuthorization(
                bundle_id=bundle_id,
                capability=capability,
                status=CapabilityStatus.VERIFIED,
                verifier=profile.verifier_mapping[capability],
            )
        if capability in profile.experimental_capabilities:
            if not allow_experimental:
                raise CapabilityUnavailable(
                    f"{capability!r} is experimental for {profile.display_name}"
                )
            return CapabilityAuthorization(
                bundle_id=bundle_id,
                capability=capability,
                status=CapabilityStatus.EXPERIMENTAL,
                verifier=profile.verifier_mapping.get(capability),
            )
        raise CapabilityUnavailable(f"{capability!r} is not declared for {profile.display_name}")


_VERIFIED = date(2026, 7, 13)


def _profile(
    bundle_id: str,
    display_name: str,
    *,
    verified: tuple[str, ...],
    experimental: tuple[str, ...],
    forbidden: tuple[str, ...],
    interfaces: tuple[InterfaceKind, ...],
    verifiers: dict[str, ProfileVerifier],
    focus: FocusPolicy,
    permissions: tuple[str, ...] = (),
) -> ApplicationProfile:
    return ApplicationProfile(
        bundle_id=bundle_id,
        display_name=display_name,
        version="1.0.0",
        required_permissions=permissions,
        verified_capabilities=verified,
        experimental_capabilities=experimental,
        forbidden_operations=forbidden,
        preferred_interface_order=interfaces,
        verifier_mapping=verifiers,
        default_focus_behaviour=focus,
        last_real_verification_date=_VERIFIED if verified else None,
    )


def build_default_application_profiles() -> ApplicationProfileRegistry:
    running = ProfileVerifier.NSWORKSPACE_RUNNING
    foreground = ProfileVerifier.NSWORKSPACE_FOREGROUND
    profiles = [
        _profile(
            "com.apple.finder",
            "Finder",
            verified=("detect_running", "detect_foreground", "launch", "focus"),
            experimental=("resolve_current_folder", "resolve_selected_files"),
            forbidden=("coordinate_click", "modify_permissions"),
            interfaces=(InterfaceKind.NATIVE_API, InterfaceKind.ACCESSIBILITY),
            verifiers={
                "detect_running": running,
                "detect_foreground": foreground,
                "launch": running,
                "focus": foreground,
            },
            focus=FocusPolicy.KEEP_NEW_FOCUS,
        ),
        _profile(
            "com.apple.TextEdit",
            "TextEdit",
            verified=("detect_running", "detect_foreground", "launch", "focus"),
            experimental=("ax_read", "ax_edit"),
            forbidden=("coordinate_click", "unrestricted_document_access"),
            interfaces=(InterfaceKind.NATIVE_API, InterfaceKind.ACCESSIBILITY),
            verifiers={
                "detect_running": running,
                "detect_foreground": foreground,
                "launch": running,
                "focus": foreground,
            },
            focus=FocusPolicy.KEEP_NEW_FOCUS,
            permissions=("accessibility_for_ax_only",),
        ),
        _profile(
            "com.microsoft.VSCode",
            "Visual Studio Code",
            verified=(
                "detect_running",
                "detect_foreground",
                "launch",
                "focus",
                "match_workspace",
            ),
            experimental=("editor_read", "editor_edit"),
            forbidden=("unrestricted_editor_control", "extension_install"),
            interfaces=(InterfaceKind.NATIVE_API, InterfaceKind.CLI, InterfaceKind.ACCESSIBILITY),
            verifiers={
                "detect_running": running,
                "detect_foreground": foreground,
                "launch": running,
                "focus": foreground,
                "match_workspace": ProfileVerifier.WORKSPACE_ASSOCIATION,
            },
            focus=FocusPolicy.KEEP_NEW_FOCUS,
            permissions=("accessibility_for_ax_only",),
        ),
        _profile(
            "com.apple.Terminal",
            "Terminal",
            verified=("detect_running", "detect_foreground", "launch", "focus"),
            experimental=("read_safe_working_directory",),
            forbidden=("execute_shell_through_ui", "read_terminal_history", "coordinate_click"),
            interfaces=(InterfaceKind.NATIVE_API,),
            verifiers={
                "detect_running": running,
                "detect_foreground": foreground,
                "launch": running,
                "focus": foreground,
            },
            focus=FocusPolicy.KEEP_NEW_FOCUS,
        ),
        _profile(
            "org.python.python",
            "THOTH Accessibility Test App",
            verified=(),
            experimental=("ax_inspect", "ax_read", "ax_edit", "ax_press"),
            forbidden=("launch_by_bundle_id", "coordinate_click", "production_use"),
            interfaces=(InterfaceKind.ACCESSIBILITY,),
            verifiers={"ax_read": ProfileVerifier.ACCESSIBILITY_VALUE},
            focus=FocusPolicy.ASK_IF_AMBIGUOUS,
            permissions=("accessibility",),
        ),
        _profile(
            "org.chromium.Chromium",
            "Chromium",
            verified=("background_read", "read_only_operations"),
            experimental=(
                "background_automation",
                "foreground_presentation",
                "form_interaction",
                "form_submission",
            ),
            forbidden=(
                "bypass_two_phase_submission",
                "browser_profile_access",
                "credential_export",
            ),
            interfaces=(InterfaceKind.BROWSER_DOM,),
            verifiers={
                "background_read": ProfileVerifier.BROWSER_URL,
                "read_only_operations": ProfileVerifier.BROWSER_URL,
            },
            focus=FocusPolicy.DO_NOT_STEAL_FOCUS,
        ),
    ]
    return ApplicationProfileRegistry(profiles)
