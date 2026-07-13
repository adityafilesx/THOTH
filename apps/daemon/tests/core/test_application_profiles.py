"""Versioned, authoritative application capability profiles."""

from datetime import date

import pytest
from pydantic import ValidationError

from thoth_daemon.core.application_profiles import (
    ApplicationProfile,
    ApplicationProfileRegistry,
    CapabilityForbidden,
    CapabilityStatus,
    CapabilityUnavailable,
    DuplicateApplicationProfile,
    InterfaceKind,
    ProfileVerifier,
    UnknownApplication,
    build_default_application_profiles,
)
from thoth_daemon.core.focus import FocusPolicy


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
        assert (
            registry.authorize(
                "com.example.Editor", "read_selection", allow_experimental=True
            ).status
            is CapabilityStatus.EXPERIMENTAL
        )

    def test_forbidden_capability_is_rejected(self) -> None:
        registry = ApplicationProfileRegistry([_profile()])
        with pytest.raises(CapabilityForbidden):
            registry.authorize("com.example.Editor", "export_credentials")

    def test_model_cannot_expand_capabilities(self) -> None:
        registry = ApplicationProfileRegistry([_profile()])
        with pytest.raises(CapabilityUnavailable):
            registry.authorize(
                "com.example.Editor", "unrestricted_control", model_requested_status="verified"
            )

    def test_model_cannot_downgrade_forbidden_operation(self) -> None:
        registry = ApplicationProfileRegistry([_profile()])
        with pytest.raises(CapabilityForbidden):
            registry.authorize(
                "com.example.Editor", "export_credentials", model_requested_status="verified"
            )

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
            "THOTH Accessibility Test App",
            "Chromium",
        }

    def test_terminal_forbids_ui_shell_execution(self) -> None:
        registry = build_default_application_profiles()
        with pytest.raises(CapabilityForbidden):
            registry.authorize("com.apple.Terminal", "execute_shell_through_ui")

    def test_chromium_separates_read_form_and_submission_capabilities(self) -> None:
        profile = build_default_application_profiles().get("org.chromium.Chromium")
        assert "background_read" in profile.verified_capabilities
        assert "form_interaction" in profile.experimental_capabilities
        assert "form_submission" in profile.experimental_capabilities
        assert "bypass_two_phase_submission" in profile.forbidden_operations
