"""Independent AX verifiers that re-read current macOS UI state."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Protocol

from omnimac_daemon.core.ax_controller import AXController
from omnimac_daemon.macos.app_control import AppControl
from omnimac_daemon.schemas.ax import (
    AXElementSnapshot,
    AXVerificationExpectation,
    AXVerificationRequest,
    AXVerificationResult,
)


class AXVerifier(Protocol):
    def verify(self, request: AXVerificationRequest, capability: str) -> AXVerificationResult: ...


class _ElementVerifier:
    expectation: AXVerificationExpectation

    def __init__(self, controller: AXController) -> None:
        self._controller = controller

    def _read(self, request: AXVerificationRequest, capability: str) -> AXElementSnapshot | None:
        if request.target is None:
            return None
        return self._controller.resolve(
            request.application_bundle_id,
            capability,
            request.target,
            verifier=request.expectation,
            verification_target=True,
        ).element

    def _result(
        self,
        request: AXVerificationRequest,
        passed: bool,
        detail: str,
        element: AXElementSnapshot | None,
    ) -> AXVerificationResult:
        return AXVerificationResult(
            passed=passed,
            expectation=request.expectation,
            observed_at=self._controller.now(),
            detail=detail,
            observed_element=element,
        )


class AXElementExistsVerifier(_ElementVerifier):
    expectation = AXVerificationExpectation.EXISTS

    def verify(self, request: AXVerificationRequest, capability: str) -> AXVerificationResult:
        element = self._read(request, capability)
        return self._result(
            request,
            element is not None,
            "element exists" if element is not None else "element does not exist",
            element,
        )


class AXElementValueVerifier(_ElementVerifier):
    expectation = AXVerificationExpectation.VALUE_EQUALS

    def verify(self, request: AXVerificationRequest, capability: str) -> AXVerificationResult:
        element = self._read(request, capability)
        metadata = element.value_metadata if element is not None else None
        passed = metadata is not None and not metadata.redacted and metadata.value == request.expected_value
        return self._result(
            request,
            passed,
            "value matched" if passed else "value did not match",
            element,
        )


class AXElementEnabledVerifier(_ElementVerifier):
    expectation = AXVerificationExpectation.ENABLED

    def verify(self, request: AXVerificationRequest, capability: str) -> AXVerificationResult:
        element = self._read(request, capability)
        passed = element is not None and element.enabled is True
        return self._result(request, passed, f"enabled={element.enabled if element else None}", element)


class AXElementFocusedVerifier(_ElementVerifier):
    expectation = AXVerificationExpectation.FOCUSED

    def verify(self, request: AXVerificationRequest, capability: str) -> AXVerificationResult:
        element = self._read(request, capability)
        passed = element is not None and element.focused is True
        return self._result(request, passed, f"focused={element.focused if element else None}", element)


class AXElementSelectedVerifier(_ElementVerifier):
    expectation = AXVerificationExpectation.SELECTED

    def verify(self, request: AXVerificationRequest, capability: str) -> AXVerificationResult:
        element = self._read(request, capability)
        passed = element is not None and element.selected is True
        return self._result(request, passed, f"selected={element.selected if element else None}", element)


class AXWindowExistsVerifier:
    expectation = AXVerificationExpectation.WINDOW_EXISTS

    def __init__(self, controller: AXController) -> None:
        self._controller = controller

    def verify(self, request: AXVerificationRequest, capability: str) -> AXVerificationResult:
        window = (
            self._controller.inspect_window(
                request.application_bundle_id,
                capability,
                request.window_identifier,
                verifier=request.expectation,
            )
            if request.window_identifier is not None
            else None
        )
        return AXVerificationResult(
            passed=window is not None,
            expectation=request.expectation,
            observed_at=self._controller.now(),
            detail="window exists" if window is not None else "window does not exist",
            observed_window=window,
        )


class AXApplicationFrontmostVerifier:
    expectation = AXVerificationExpectation.APPLICATION_FRONTMOST

    def __init__(
        self,
        app_control: AppControl,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._app_control = app_control
        self._clock = clock or (lambda: datetime.now(UTC))

    def verify(self, request: AXVerificationRequest, capability: str) -> AXVerificationResult:
        del capability
        frontmost = self._app_control.frontmost()
        passed = frontmost is not None and frontmost.bundle_id == request.application_bundle_id
        return AXVerificationResult(
            passed=passed,
            expectation=request.expectation,
            observed_at=self._clock(),
            detail=f"frontmost bundle={frontmost.bundle_id if frontmost else None!r}",
        )


class AXCompositeVerifier:
    def __init__(self, verifiers: Sequence[AXVerifier]) -> None:
        self._verifiers = tuple(verifiers)

    def verify_all(
        self,
        requests: Sequence[AXVerificationRequest],
        capability: str,
    ) -> AXVerificationResult:
        if not requests or len(requests) != len(self._verifiers):
            raise ValueError("composite AX verification requires one request per verifier")
        results = [verifier.verify(request, capability) for verifier, request in zip(self._verifiers, requests, strict=True)]
        passed = all(result.passed for result in results)
        return AXVerificationResult(
            passed=passed,
            expectation=results[-1].expectation,
            observed_at=max(result.observed_at for result in results),
            detail="; ".join(f"{result.expectation.value}={'ok' if result.passed else 'fail'}: {result.detail}" for result in results),
        )


class AXVerifierDispatcher:
    def __init__(
        self,
        controller: AXController,
        app_control: AppControl | None = None,
    ) -> None:
        self._controller = controller
        self._app_control = app_control

    def verify(
        self,
        request: AXVerificationRequest,
        capability: str,
    ) -> AXVerificationResult:
        element_verifiers: dict[AXVerificationExpectation, AXVerifier] = {
            AXVerificationExpectation.EXISTS: AXElementExistsVerifier(self._controller),
            AXVerificationExpectation.VALUE_EQUALS: AXElementValueVerifier(self._controller),
            AXVerificationExpectation.ENABLED: AXElementEnabledVerifier(self._controller),
            AXVerificationExpectation.FOCUSED: AXElementFocusedVerifier(self._controller),
            AXVerificationExpectation.SELECTED: AXElementSelectedVerifier(self._controller),
            AXVerificationExpectation.WINDOW_EXISTS: AXWindowExistsVerifier(self._controller),
        }
        verifier = element_verifiers.get(request.expectation)
        if verifier is not None:
            return verifier.verify(request, capability)
        if request.expectation is AXVerificationExpectation.APPLICATION_FRONTMOST and self._app_control is not None:
            return AXApplicationFrontmostVerifier(
                self._app_control,
                self._controller.now,
            ).verify(request, capability)
        return AXVerificationResult(
            passed=False,
            expectation=request.expectation,
            observed_at=self._controller.now(),
            detail="required AX verifier is unavailable",
        )
