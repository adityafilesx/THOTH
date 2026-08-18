"""Versioned, authoritative application capability profiles."""

from datetime import date

import pytest
from pydantic import ValidationError

from omnimac_daemon.core.application_profiles import (
    ApplicationProfile,
    ApplicationProfileRegistry,
    AXCapabilityRule,
    CapabilityForbidden,
    CapabilityStatus,
    CapabilityTargetForbidden,
    CapabilityUnavailable,
    DuplicateApplicationProfile,
    InterfaceKind,
    ProfileVerifier,
    UnknownApplication,
    build_default_application_profiles,
)
from omnimac_daemon.core.focus import FocusPolicy
from omnimac_daemon.schemas import RiskLevel
from omnimac_daemon.schemas.ax import AXVerificationExpectation


def _profile(**updates: object) -> ApplicationProfile:
    values: dict[str, object] = {
        "bundle_id": "com.example.Editor",
        "display_name": "Editor",
        "version": "1.2.3",
        "required_permissions": [],
        "verified_capabilities": ["detect_running"],
        "experimental_capabilities": ["read_selection"],
        "forbidden_operations": ["export_credentials"],
        "preferred_interface_order": [InterfaceKind.NATIVE_API, InterfaceKind.ACCESSIBILITY],
        "verifier_mapping": {"detect_running": ProfileVerifier.NSWORKSPACE_RUNNING},
        "default_focus_behaviour": FocusPolicy.DO_NOT_STEAL_FOCUS,
        "last_real_verification_date": date(2026, 7, 13),
    }
    values.update(updates)
    return ApplicationProfile(**values)


class TestProfileValidation:
    def test_profile_version_parsing(self) -> None:
        profile = _profile(version="2.10.4")
        assert profile.version_tuple == (2, 10, 4)

    @pytest.mark.parametrize("version", ["1", "1.2", "v1.2.3", "1.2.3.4", "latest"])
    def test_invalid_profile_version_rejected(self, version: str) -> None:
        with pytest.raises(ValidationError):
            _profile(version=version)

    def test_missing_bundle_identifier_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _profile(bundle_id="")

    def test_overlapping_capability_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _profile(experimental_capabilities=["detect_running"])

    def test_invalid_verifier_mapping_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _profile(verifier_mapping={"unknown_capability": ProfileVerifier.FILE_EXISTS})

    def test_verified_capability_requires_verifier(self) -> None:
        with pytest.raises(ValidationError):
            _profile(verifier_mapping={})


class TestRegistryAuthority:
    def test_unknown_application_fails_closed(self) -> None:
        registry = ApplicationProfileRegistry([_profile()])
        with pytest.raises(UnknownApplication):
            registry.authorize("com.unknown.App", "detect_running")

    def test_verified_capability_is_authorized(self) -> None:
        registry = ApplicationProfileRegistry([_profile()])
        result = registry.authorize("com.example.Editor", "detect_running")
        assert result.status is CapabilityStatus.VERIFIED
        assert result.verifier is ProfileVerifier.NSWORKSPACE_RUNNING

    def test_experimental_capability_requires_opt_in(self) -> None:
        registry = ApplicationProfileRegistry([_profile()])
        with pytest.raises(CapabilityUnavailable, match="experimental"):
            registry.authorize("com.example.Editor", "read_selection")
        assert registry.authorize("com.example.Editor", "read_selection", allow_experimental=True).status is CapabilityStatus.EXPERIMENTAL

    def test_forbidden_capability_is_rejected(self) -> None:
        registry = ApplicationProfileRegistry([_profile()])
        with pytest.raises(CapabilityForbidden):
            registry.authorize("com.example.Editor", "export_credentials")

    def test_model_cannot_expand_capabilities(self) -> None:
        registry = ApplicationProfileRegistry([_profile()])
        with pytest.raises(CapabilityUnavailable):
            registry.authorize("com.example.Editor", "unrestricted_control", model_requested_status="verified")

    def test_model_cannot_downgrade_forbidden_operation(self) -> None:
        registry = ApplicationProfileRegistry([_profile()])
        with pytest.raises(CapabilityForbidden):
            registry.authorize("com.example.Editor", "export_credentials", model_requested_status="verified")

    def test_duplicate_profile_rejected(self) -> None:
        with pytest.raises(DuplicateApplicationProfile):
            ApplicationProfileRegistry([_profile(), _profile(display_name="Other")])


class TestDefaultProfiles:
    def test_six_required_profiles_exist(self) -> None:
        registry = build_default_application_profiles()
        assert {p.display_name for p in registry.all()} == {
            "Finder",
            "TextEdit",
            "Visual Studio Code",
            "Terminal",
            "OmniMac Accessibility Test App",
            "Chromium",
        }

    def test_terminal_forbids_ui_shell_execution(self) -> None:
        registry = build_default_application_profiles()
        with pytest.raises(CapabilityForbidden):
            registry.authorize("com.apple.Terminal", "execute_shell_through_ui")

    def test_vscode_workspace_match_is_verified_by_authoritative_association(self) -> None:
        result = build_default_application_profiles().authorize("com.microsoft.VSCode", "match_workspace")
        assert result.status is CapabilityStatus.VERIFIED
        assert result.verifier is ProfileVerifier.WORKSPACE_ASSOCIATION

    def test_chromium_separates_read_form_and_submission_capabilities(self) -> None:
        profile = build_default_application_profiles().get("org.chromium.Chromium")
        assert "background_read" in profile.verified_capabilities
        assert "form_interaction" in profile.experimental_capabilities
        assert "form_submission" in profile.experimental_capabilities
        assert "bypass_two_phase_submission" in profile.forbidden_operations

    def test_native_ax_fixture_uses_unique_bundle_and_no_unverified_promotion(self) -> None:
        profile = build_default_application_profiles().get("me.adityalabs.omnimac.axtest")
        assert profile.display_name == "OmniMac Accessibility Test App"
        assert not {capability for capability in profile.verified_capabilities if capability.startswith("ax_")}
        assert "ax_set_value" in profile.experimental_capabilities
        assert "ax_set_value" in profile.ax_capability_rules

    def test_ax_rule_binds_tool_target_action_risk_focus_and_verifier(self) -> None:
        rule = AXCapabilityRule(
            tool_name="ax.perform_action",
            allowed_identifiers=("ax-save-button",),
            allowed_roles=("AXButton",),
            allowed_verifier_identifiers=("ax-save-button",),
            allowed_actions=("AXPress",),
            allowed_verifiers=(AXVerificationExpectation.VALUE_EQUALS,),
            default_risk=RiskLevel.R1,
            focus_policy=FocusPolicy.RESTORE_PREVIOUS_FOCUS,
        )
        profile = _profile(
            verified_capabilities=["ax_save"],
            experimental_capabilities=[],
            verifier_mapping={"ax_save": ProfileVerifier.ACCESSIBILITY_VALUE},
            ax_capability_rules={"ax_save": rule},
        )
        registry = ApplicationProfileRegistry([profile])
        registry.authorize_ax(
            profile.bundle_id,
            "ax_save",
            tool_name="ax.perform_action",
            identifier="ax-save-button",
            role="AXButton",
            action="AXPress",
            verifier=AXVerificationExpectation.VALUE_EQUALS,
            verification_target=True,
        )
        with pytest.raises(CapabilityTargetForbidden):
            registry.authorize_ax(
                profile.bundle_id,
                "ax_save",
                tool_name="ax.perform_action",
                identifier="ax-delete-button",
                role="AXButton",
                action="AXPress",
                verifier=AXVerificationExpectation.VALUE_EQUALS,
                verification_target=True,
            )

    def test_terminal_ax_is_snapshot_only_and_chromium_prefers_dom(self) -> None:
        registry = build_default_application_profiles()
        terminal = registry.get("com.apple.Terminal")
        chromium = registry.get("org.chromium.Chromium")
        assert set(terminal.ax_capability_rules) == {
            "ax_inspect_application",
            "ax_inspect_window",
        }
        assert "ax_set_value" not in terminal.ax_capability_rules
        assert chromium.preferred_interface_order[0] is InterfaceKind.BROWSER_DOM
        assert set(chromium.ax_capability_rules) == {
            "ax_inspect_application",
            "ax_inspect_window",
        }

    def test_fixture_action_and_independent_status_target_are_separately_bound(self) -> None:
        registry = build_default_application_profiles()
        bundle_id = "me.adityalabs.omnimac.axtest"
        registry.authorize_ax(
            bundle_id,
            "ax_perform_action",
            tool_name="ax.perform_action",
            identifier="ax-save-button",
            role="AXButton",
            action="AXPress",
            allow_experimental=True,
            resolved_target=True,
        )
        registry.authorize_ax(
            bundle_id,
            "ax_perform_action",
            tool_name="ax.perform_action",
            identifier="ax-status-label",
            verifier=AXVerificationExpectation.VALUE_EQUALS,
            allow_experimental=True,
            verification_target=True,
        )

    def test_ax_rule_must_reference_declared_capability(self) -> None:
        with pytest.raises(ValidationError):
            _profile(
                ax_capability_rules={
                    "invented": AXCapabilityRule(
                        tool_name="ax.read_value",
                        allowed_identifiers=("field",),
                        allowed_verifiers=(AXVerificationExpectation.VALUE_EQUALS,),
                        default_risk=RiskLevel.R0,
                        focus_policy=FocusPolicy.DO_NOT_STEAL_FOCUS,
                    )
                }
            )

    def test_declared_ax_capability_requires_a_rule(self) -> None:
        with pytest.raises(ValidationError, match="authoritative rules"):
            _profile(
                verified_capabilities=["ax_read_value"],
                experimental_capabilities=[],
                verifier_mapping={"ax_read_value": ProfileVerifier.ACCESSIBILITY_VALUE},
            )

    def test_registry_returns_copies_not_mutable_authority(self) -> None:
        source = build_default_application_profiles().get("me.adityalabs.omnimac.axtest")
        registry = ApplicationProfileRegistry([source])
        returned = registry.get("me.adityalabs.omnimac.axtest")
        returned.ax_capability_rules["model_invented"] = AXCapabilityRule(
            tool_name="ax.read_value",
            allowed_identifiers=("anything",),
            default_risk=RiskLevel.R0,
            focus_policy=FocusPolicy.DO_NOT_STEAL_FOCUS,
        )
        assert "model_invented" not in registry.get(returned.bundle_id).ax_capability_rules
        with pytest.raises(CapabilityUnavailable):
            registry.authorize(returned.bundle_id, "model_invented", allow_experimental=True)

        source.ax_capability_rules.clear()
        assert "ax_set_value" in registry.get(returned.bundle_id).ax_capability_rules

    def test_registered_tool_cannot_understate_profile_risk(self) -> None:
        profile = _profile(
            verified_capabilities=["ax_save"],
            experimental_capabilities=[],
            verifier_mapping={"ax_save": ProfileVerifier.ACCESSIBILITY_VALUE},
            ax_capability_rules={
                "ax_save": AXCapabilityRule(
                    tool_name="ax.set_value",
                    allowed_identifiers=("field",),
                    allowed_verifier_identifiers=("field",),
                    allowed_verifiers=(AXVerificationExpectation.VALUE_EQUALS,),
                    default_risk=RiskLevel.R1,
                    focus_policy=FocusPolicy.RESTORE_PREVIOUS_FOCUS,
                )
            },
        )
        registry = ApplicationProfileRegistry([profile])
        with pytest.raises(CapabilityTargetForbidden, match="risk conflicts"):
            registry.validate_ax_tool_contract(
                "ax.set_value",
                RiskLevel.R0,
                FocusPolicy.RESTORE_PREVIOUS_FOCUS,
            )
