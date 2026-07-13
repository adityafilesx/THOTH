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
from thoth_daemon.schemas import RiskLevel
from thoth_daemon.schemas.ax import AXVerificationExpectation


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


class AXCapabilityRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str = Field(pattern=r"^ax\.[a-z_]+$")
    allowed_identifiers: tuple[str, ...] = ()
    allowed_roles: tuple[str, ...] = ()
    allowed_verifier_identifiers: tuple[str, ...] = ()
    allowed_verifier_roles: tuple[str, ...] = ()
    allowed_actions: tuple[str, ...] = ()
    allowed_verifiers: tuple[AXVerificationExpectation, ...] = ()
    default_risk: RiskLevel
    focus_policy: FocusPolicy

    @model_validator(mode="after")
    def _safe_floor(self) -> AXCapabilityRule:
        mutation = self.tool_name in {
            "ax.set_value",
            "ax.perform_action",
            "ax.select_option",
        }
        if mutation and self.default_risk.rank < RiskLevel.R1.rank:
            raise ValueError("AX mutation rule cannot have a risk below R1")
        if self.tool_name == "ax.perform_action" and not self.allowed_actions:
            raise ValueError("AX perform_action rule requires an action allowlist")
        for name, values in (
            ("identifier", self.allowed_identifiers),
            ("role", self.allowed_roles),
            ("verifier identifier", self.allowed_verifier_identifiers),
            ("verifier role", self.allowed_verifier_roles),
            ("action", self.allowed_actions),
            ("verifier", self.allowed_verifiers),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"AX {name} allowlist cannot contain duplicates")
        return self


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
    ax_capability_rules: dict[str, AXCapabilityRule] = Field(default_factory=dict)

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
        undeclared_rules = set(self.ax_capability_rules) - (groups[0] | groups[1])
        if undeclared_rules:
            raise ValueError(f"AX rules reference undeclared capabilities: {undeclared_rules}")
        missing_rules = {
            capability
            for capability in groups[0] | groups[1]
            if capability.startswith("ax_") and capability not in self.ax_capability_rules
        }
        if missing_rules:
            raise ValueError(f"AX capabilities require authoritative rules: {missing_rules}")
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


class CapabilityTargetForbidden(ApplicationProfileError):
    pass


class ApplicationProfileRegistry:
    def __init__(self, profiles: list[ApplicationProfile]) -> None:
        self._profiles: dict[str, ApplicationProfile] = {}
        for profile in profiles:
            if profile.bundle_id in self._profiles:
                raise DuplicateApplicationProfile(
                    f"duplicate application profile for {profile.bundle_id!r}"
                )
            self._profiles[profile.bundle_id] = profile.model_copy(deep=True)

    def all(self) -> tuple[ApplicationProfile, ...]:
        return tuple(profile.model_copy(deep=True) for profile in self._profiles.values())

    def get(self, bundle_id: str) -> ApplicationProfile:
        return self._get(bundle_id).model_copy(deep=True)

    def _get(self, bundle_id: str) -> ApplicationProfile:
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
        profile = self._get(bundle_id)
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

    def authorize_ax(
        self,
        bundle_id: str,
        capability: str,
        *,
        tool_name: str,
        identifier: str | None = None,
        role: str | None = None,
        action: str | None = None,
        verifier: AXVerificationExpectation | None = None,
        allow_experimental: bool = False,
        resolved_target: bool = False,
        require_target: bool = True,
        verification_target: bool = False,
    ) -> CapabilityAuthorization:
        authorization = self.authorize(
            bundle_id,
            capability,
            allow_experimental=allow_experimental,
        )
        profile = self._get(bundle_id)
        rule = self.ax_rule(bundle_id, capability)
        if rule.tool_name != tool_name:
            raise CapabilityTargetForbidden(
                f"{capability!r} does not authorize {tool_name!r} for {profile.display_name}"
            )
        allowed_identifiers = (
            rule.allowed_verifier_identifiers if verification_target else rule.allowed_identifiers
        )
        allowed_roles = rule.allowed_verifier_roles if verification_target else rule.allowed_roles
        identifier_allowed = identifier in allowed_identifiers if identifier else False
        role_allowed = role in allowed_roles if role else False
        if identifier is not None and allowed_identifiers and not identifier_allowed:
            raise CapabilityTargetForbidden("AX identifier is outside the capability rule")
        if role is not None and allowed_roles and not role_allowed:
            raise CapabilityTargetForbidden("AX role is outside the capability rule")
        has_target_rules = bool(allowed_identifiers or allowed_roles)
        if verification_target and require_target and not has_target_rules:
            raise CapabilityTargetForbidden("AX verifier target has no authorized selector rule")
        if require_target and has_target_rules and not (identifier_allowed or role_allowed):
            raise CapabilityTargetForbidden("AX target has no authorized semantic selector")
        if resolved_target:
            if allowed_identifiers and not identifier_allowed:
                raise CapabilityTargetForbidden("resolved AX identifier is outside the rule")
            if allowed_roles and not role_allowed:
                raise CapabilityTargetForbidden("resolved AX role is outside the rule")
        if action is not None and action not in rule.allowed_actions:
            raise CapabilityTargetForbidden("AX action is outside the capability rule")
        if verifier is not None and verifier not in rule.allowed_verifiers:
            raise CapabilityTargetForbidden("AX verifier is outside the capability rule")
        return authorization

    def ax_rule(self, bundle_id: str, capability: str) -> AXCapabilityRule:
        profile = self._get(bundle_id)
        rule = profile.ax_capability_rules.get(capability)
        if rule is None:
            raise CapabilityTargetForbidden(
                f"{capability!r} has no AX rule for {profile.display_name}"
            )
        return rule.model_copy(deep=True)

    def validate_ax_tool_contract(
        self,
        tool_name: str,
        default_risk: RiskLevel,
        focus_policy: FocusPolicy,
    ) -> None:
        for profile in self._profiles.values():
            for rule in profile.ax_capability_rules.values():
                if rule.tool_name != tool_name:
                    continue
                if rule.default_risk is not default_risk:
                    raise CapabilityTargetForbidden(
                        f"{tool_name!r} risk conflicts with {profile.display_name} profile"
                    )
                if rule.focus_policy is not focus_policy:
                    raise CapabilityTargetForbidden(
                        f"{tool_name!r} focus conflicts with {profile.display_name} profile"
                    )


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
    ax_rules: dict[str, AXCapabilityRule] | None = None,
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
        ax_capability_rules=dict(ax_rules or {}),
    )


def build_default_application_profiles() -> ApplicationProfileRegistry:
    running = ProfileVerifier.NSWORKSPACE_RUNNING
    foreground = ProfileVerifier.NSWORKSPACE_FOREGROUND
    read_focus = FocusPolicy.DO_NOT_STEAL_FOCUS
    mutation_focus = FocusPolicy.RESTORE_PREVIOUS_FOCUS
    snapshot_capabilities = ("ax_inspect_application", "ax_inspect_window")
    snapshot_rules = {
        capability: AXCapabilityRule(
            tool_name=capability.replace("_", ".", 1),
            default_risk=RiskLevel.R0,
            focus_policy=read_focus,
        )
        for capability in snapshot_capabilities
    }
    fixture_identifiers = (
        "ax-single-line-input",
        "ax-multiline-input",
        "ax-checkbox",
        "ax-toggle",
        "ax-picker",
        "ax-stepper",
        "ax-item-list",
        "ax-search-field",
        "ax-disabled-button",
        "ax-save-button",
        "ax-modal-button",
        "ax-confirm-alert-button",
        "ax-status-label",
        "ax-progress",
        "ax-segmented-control",
        "ax-moving-control",
        "ax-delayed-control",
        "ax-disappearing-control",
        "ax-validation-error",
        "ax-reset-button",
    )
    fixture_capabilities = (
        "ax_inspect_application",
        "ax_inspect_window",
        "ax_find_element",
        "ax_read_value",
        "ax_set_value",
        "ax_perform_action",
        "ax_select_option",
        "ax_wait_for_element",
        "ax_wait_for_value",
        "ax_list_supported_actions",
    )
    fixture_rules = {
        **snapshot_rules,
        **{
            capability: AXCapabilityRule(
                tool_name=capability.replace("_", ".", 1),
                allowed_identifiers=fixture_identifiers,
                allowed_verifier_identifiers=fixture_identifiers,
                allowed_verifiers=(
                    AXVerificationExpectation.EXISTS,
                    AXVerificationExpectation.VALUE_EQUALS,
                    AXVerificationExpectation.ENABLED,
                    AXVerificationExpectation.FOCUSED,
                    AXVerificationExpectation.SELECTED,
                ),
                default_risk=RiskLevel.R0,
                focus_policy=read_focus,
            )
            for capability in (
                "ax_find_element",
                "ax_read_value",
                "ax_wait_for_element",
                "ax_wait_for_value",
                "ax_list_supported_actions",
            )
        },
        "ax_set_value": AXCapabilityRule(
            tool_name="ax.set_value",
            allowed_identifiers=(
                "ax-single-line-input",
                "ax-multiline-input",
                "ax-checkbox",
                "ax-toggle",
                "ax-stepper",
            ),
            allowed_verifier_identifiers=(
                "ax-single-line-input",
                "ax-multiline-input",
                "ax-checkbox",
                "ax-toggle",
                "ax-stepper",
            ),
            allowed_verifiers=(AXVerificationExpectation.VALUE_EQUALS,),
            default_risk=RiskLevel.R1,
            focus_policy=mutation_focus,
        ),
        "ax_perform_action": AXCapabilityRule(
            tool_name="ax.perform_action",
            allowed_identifiers=(
                "ax-save-button",
                "ax-modal-button",
                "ax-confirm-alert-button",
                "ax-moving-control",
                "ax-disappearing-control",
                "ax-reset-button",
            ),
            allowed_roles=("AXButton",),
            allowed_verifier_identifiers=fixture_identifiers,
            allowed_actions=("AXPress", "AXConfirm", "AXCancel"),
            allowed_verifiers=(
                AXVerificationExpectation.VALUE_EQUALS,
                AXVerificationExpectation.WINDOW_EXISTS,
                AXVerificationExpectation.ENABLED,
                AXVerificationExpectation.FOCUSED,
                AXVerificationExpectation.SELECTED,
                AXVerificationExpectation.APPLICATION_FRONTMOST,
            ),
            default_risk=RiskLevel.R1,
            focus_policy=mutation_focus,
        ),
        "ax_select_option": AXCapabilityRule(
            tool_name="ax.select_option",
            allowed_identifiers=("ax-picker", "ax-segmented-control"),
            allowed_verifier_identifiers=("ax-picker", "ax-segmented-control"),
            allowed_verifiers=(AXVerificationExpectation.VALUE_EQUALS,),
            default_risk=RiskLevel.R1,
            focus_policy=mutation_focus,
        ),
    }
    profiles = [
        _profile(
            "com.apple.finder",
            "Finder",
            verified=("detect_running", "detect_foreground", "launch", "focus"),
            experimental=(
                "resolve_current_folder",
                "resolve_selected_files",
                *snapshot_capabilities,
            ),
            forbidden=("coordinate_click", "modify_permissions"),
            interfaces=(InterfaceKind.NATIVE_API, InterfaceKind.ACCESSIBILITY),
            verifiers={
                "detect_running": running,
                "detect_foreground": foreground,
                "launch": running,
                "focus": foreground,
            },
            focus=FocusPolicy.KEEP_NEW_FOCUS,
            permissions=("accessibility_for_ax_only",),
            ax_rules=snapshot_rules,
        ),
        _profile(
            "com.apple.TextEdit",
            "TextEdit",
            verified=("detect_running", "detect_foreground", "launch", "focus"),
            experimental=(
                "ax_inspect_application",
                "ax_inspect_window",
                "ax_find_element",
                "ax_read_value",
                "ax_set_value",
            ),
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
            ax_rules={
                **snapshot_rules,
                **{
                    capability: AXCapabilityRule(
                        tool_name=capability.replace("_", ".", 1),
                        allowed_roles=("AXTextArea",),
                        allowed_verifier_roles=(
                            ("AXTextArea",) if capability == "ax_set_value" else ()
                        ),
                        allowed_verifiers=(AXVerificationExpectation.VALUE_EQUALS,),
                        default_risk=(
                            RiskLevel.R1 if capability == "ax_set_value" else RiskLevel.R0
                        ),
                        focus_policy=(
                            mutation_focus if capability == "ax_set_value" else read_focus
                        ),
                    )
                    for capability in ("ax_find_element", "ax_read_value", "ax_set_value")
                },
            },
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
            experimental=(
                "editor_read",
                "editor_edit",
                "ax_inspect_application",
                "ax_inspect_window",
                "ax_find_element",
                "ax_read_value",
            ),
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
            ax_rules={
                **snapshot_rules,
                **{
                    capability: AXCapabilityRule(
                        tool_name=capability.replace("_", ".", 1),
                        allowed_roles=("AXTextArea",),
                        allowed_verifiers=(AXVerificationExpectation.VALUE_EQUALS,),
                        default_risk=RiskLevel.R0,
                        focus_policy=read_focus,
                    )
                    for capability in ("ax_find_element", "ax_read_value")
                },
            },
        ),
        _profile(
            "com.apple.Terminal",
            "Terminal",
            verified=("detect_running", "detect_foreground", "launch", "focus"),
            experimental=("read_safe_working_directory", *snapshot_capabilities),
            forbidden=("execute_shell_through_ui", "read_terminal_history", "coordinate_click"),
            interfaces=(InterfaceKind.NATIVE_API, InterfaceKind.ACCESSIBILITY),
            verifiers={
                "detect_running": running,
                "detect_foreground": foreground,
                "launch": running,
                "focus": foreground,
            },
            focus=FocusPolicy.KEEP_NEW_FOCUS,
            permissions=("accessibility_for_ax_only",),
            ax_rules=snapshot_rules,
        ),
        _profile(
            "me.adityalabs.thoth.axtest",
            "THOTH Accessibility Test App",
            verified=(),
            experimental=fixture_capabilities,
            forbidden=("coordinate_click", "production_use", "credential_dialog"),
            interfaces=(InterfaceKind.ACCESSIBILITY,),
            verifiers={},
            focus=FocusPolicy.ASK_IF_AMBIGUOUS,
            permissions=("accessibility",),
            ax_rules=fixture_rules,
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
                *snapshot_capabilities,
            ),
            forbidden=(
                "bypass_two_phase_submission",
                "browser_profile_access",
                "credential_export",
            ),
            interfaces=(InterfaceKind.BROWSER_DOM, InterfaceKind.ACCESSIBILITY),
            verifiers={
                "background_read": ProfileVerifier.BROWSER_URL,
                "read_only_operations": ProfileVerifier.BROWSER_URL,
            },
            focus=FocusPolicy.DO_NOT_STEAL_FOCUS,
            permissions=("accessibility_for_ax_only",),
            ax_rules=snapshot_rules,
        ),
    ]
    return ApplicationProfileRegistry(profiles)
