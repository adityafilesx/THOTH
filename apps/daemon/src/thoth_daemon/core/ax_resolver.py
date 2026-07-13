"""Deterministic, capability-gated semantic AX element resolution."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from thoth_daemon.schemas.ax import AXElementQuery, AXElementReference, AXElementSnapshot


class AXResolutionMethod(StrEnum):
    REFERENCE = "reference"
    IDENTIFIER = "identifier"
    EXACT_ROLE_LABEL = "exact_role_label"
    NORMALIZED_ROLE_LABEL = "normalized_role_label"
    PROFILE_ALIAS = "profile_alias"
    PARENT_PATH = "parent_path"
    FUZZY = "fuzzy"


class AXResolutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    element: AXElementSnapshot | None = None
    method: AXResolutionMethod | None = None
    confidence: float = Field(ge=0, le=1)
    candidate_count: int = Field(ge=0)
    ambiguous: bool
    rejection_reason: str | None = None
    freshness_timestamp: datetime
    re_resolved: bool = False


class AXResolver:
    def __init__(
        self,
        *,
        max_age: timedelta = timedelta(seconds=2),
        max_elements: int = 500,
        max_fuzzy_candidates: int = 50,
        fuzzy_threshold: float = 0.88,
        fuzzy_separation: float = 0.05,
    ) -> None:
        if max_age <= timedelta(0):
            raise ValueError("max_age must be positive")
        if not 0 < max_elements <= 500:
            raise ValueError("max_elements must be between 1 and 500")
        if not 0 < max_fuzzy_candidates <= 50:
            raise ValueError("max_fuzzy_candidates must be between 1 and 50")
        self._max_age = max_age
        self._max_elements = max_elements
        self._max_fuzzy_candidates = max_fuzzy_candidates
        self._fuzzy_threshold = fuzzy_threshold
        self._fuzzy_separation = fuzzy_separation

    def resolve(
        self,
        query: AXElementQuery,
        elements: Sequence[AXElementSnapshot],
        *,
        now: datetime,
        capability_authorized: bool,
        trusted_aliases: Mapping[str, AXElementQuery] | None = None,
        reference: AXElementReference | None = None,
        require_enabled: bool = False,
    ) -> AXResolutionResult:
        freshness = max((element.captured_at for element in elements), default=now)
        if not capability_authorized:
            return self._reject("application capability is not authorized", freshness)
        if len(elements) > self._max_elements:
            return self._reject(
                f"AX snapshot exceeds the {self._max_elements}-element safety ceiling",
                freshness,
            )

        app_elements = [
            element
            for element in elements
            if element.application_bundle_id == query.application_bundle_id
        ]
        if elements and not app_elements:
            return self._reject("AX elements belong to a different application", freshness)
        scoped = [
            element
            for element in app_elements
            if query.window_identifier is None
            or element.window_identifier == query.window_identifier
        ]
        eligible = [
            element
            for element in scoped
            if element.visible is not False and self._is_fresh(element, now)
        ]

        re_resolved = False
        if reference is not None:
            if reference.application_bundle_id != query.application_bundle_id:
                return self._reject("AX reference belongs to a different application", freshness)
            reference_matches = [
                element for element in eligible if element.reference_id == reference.reference_id
            ]
            if now < reference.expires_at and len(reference_matches) == 1:
                return self._resolved(
                    reference_matches[0],
                    AXResolutionMethod.REFERENCE,
                    1.0,
                    1,
                    freshness,
                    require_enabled=require_enabled,
                )
            re_resolved = True

        if query.identifier is not None:
            candidates = [
                element
                for element in eligible
                if element.identifier == query.identifier and self._role_matches(query, element)
            ]
            result = self._candidate_result(
                candidates,
                AXResolutionMethod.IDENTIFIER,
                1.0,
                freshness,
                require_enabled,
                re_resolved,
            )
            if result is not None:
                return result

        if query.role is not None and query.label is not None:
            candidates = [
                element
                for element in eligible
                if self._role_matches(query, element) and element.label == query.label
            ]
            result = self._candidate_result(
                candidates,
                AXResolutionMethod.EXACT_ROLE_LABEL,
                0.99,
                freshness,
                require_enabled,
                re_resolved,
            )
            if result is not None:
                return result

            normalized_label = _normalize(query.label)
            candidates = [
                element
                for element in eligible
                if self._role_matches(query, element)
                and element.label is not None
                and _normalize(element.label) == normalized_label
            ]
            result = self._candidate_result(
                candidates,
                AXResolutionMethod.NORMALIZED_ROLE_LABEL,
                0.96,
                freshness,
                require_enabled,
                re_resolved,
            )
            if result is not None:
                return result

        if query.semantic_alias is not None:
            alias = (trusted_aliases or {}).get(query.semantic_alias)
            if alias is None:
                return self._reject(
                    "semantic alias is not declared by the trusted profile", freshness
                )
            if (
                alias.application_bundle_id != query.application_bundle_id
                or alias.semantic_alias is not None
            ):
                return self._reject(
                    "trusted profile alias is invalid for this application", freshness
                )
            aliased = self.resolve(
                alias,
                elements,
                now=now,
                capability_authorized=True,
                trusted_aliases={},
                require_enabled=require_enabled,
            )
            if aliased.element is None:
                return aliased.model_copy(update={"re_resolved": re_resolved})
            return aliased.model_copy(
                update={
                    "method": AXResolutionMethod.PROFILE_ALIAS,
                    "confidence": min(aliased.confidence, 0.97),
                    "re_resolved": re_resolved,
                }
            )

        if query.parent_path:
            candidates = [
                element
                for element in eligible
                if element.parent_path == query.parent_path and self._role_matches(query, element)
            ]
            result = self._candidate_result(
                candidates,
                AXResolutionMethod.PARENT_PATH,
                0.93,
                freshness,
                require_enabled,
                re_resolved,
            )
            if result is not None:
                return result

        if query.role is not None and query.label is not None:
            fuzzy_candidates = [
                element
                for element in eligible
                if self._role_matches(query, element) and element.label is not None
            ]
            if len(fuzzy_candidates) > self._max_fuzzy_candidates:
                return self._reject(
                    "too many candidates for bounded fuzzy resolution", freshness, re_resolved
                )
            fuzzy = self._fuzzy_result(
                query.label,
                fuzzy_candidates,
                freshness,
                require_enabled,
                re_resolved,
            )
            if fuzzy is not None:
                return fuzzy

        reason = self._diagnose_unavailable(query, scoped, now, require_enabled)
        return self._reject(reason, freshness, re_resolved)

    def _is_fresh(self, element: AXElementSnapshot, now: datetime) -> bool:
        age = now - element.captured_at
        return timedelta(0) <= age <= self._max_age

    @staticmethod
    def _role_matches(query: AXElementQuery, element: AXElementSnapshot) -> bool:
        if query.role is not None and element.role != query.role:
            return False
        return query.subrole is None or element.subrole == query.subrole

    def _candidate_result(
        self,
        candidates: list[AXElementSnapshot],
        method: AXResolutionMethod,
        confidence: float,
        freshness: datetime,
        require_enabled: bool,
        re_resolved: bool,
    ) -> AXResolutionResult | None:
        if not candidates:
            return None
        if len(candidates) > 1:
            return AXResolutionResult(
                confidence=confidence,
                candidate_count=len(candidates),
                ambiguous=True,
                rejection_reason="multiple plausible AX elements require clarification",
                freshness_timestamp=freshness,
                re_resolved=re_resolved,
            )
        return self._resolved(
            candidates[0],
            method,
            confidence,
            1,
            freshness,
            require_enabled=require_enabled,
            re_resolved=re_resolved,
        )

    def _fuzzy_result(
        self,
        label: str,
        candidates: list[AXElementSnapshot],
        freshness: datetime,
        require_enabled: bool,
        re_resolved: bool,
    ) -> AXResolutionResult | None:
        wanted = _normalize(label)
        ranked = sorted(
            (
                (SequenceMatcher(None, wanted, _normalize(element.label or "")).ratio(), element)
                for element in candidates
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] < self._fuzzy_threshold:
            return None
        if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < self._fuzzy_separation:
            return AXResolutionResult(
                confidence=ranked[0][0],
                candidate_count=2,
                ambiguous=True,
                rejection_reason="fuzzy AX candidates are too close; clarification required",
                freshness_timestamp=freshness,
                re_resolved=re_resolved,
            )
        return self._resolved(
            ranked[0][1],
            AXResolutionMethod.FUZZY,
            ranked[0][0],
            1,
            freshness,
            require_enabled=require_enabled,
            re_resolved=re_resolved,
        )

    @staticmethod
    def _resolved(
        element: AXElementSnapshot,
        method: AXResolutionMethod,
        confidence: float,
        candidate_count: int,
        freshness: datetime,
        *,
        require_enabled: bool,
        re_resolved: bool = False,
    ) -> AXResolutionResult:
        if require_enabled and element.enabled is not True:
            return AXResolutionResult(
                confidence=confidence,
                candidate_count=candidate_count,
                ambiguous=False,
                rejection_reason="resolved AX element is disabled",
                freshness_timestamp=freshness,
                re_resolved=re_resolved,
            )
        return AXResolutionResult(
            element=element,
            method=method,
            confidence=confidence,
            candidate_count=candidate_count,
            ambiguous=False,
            freshness_timestamp=freshness,
            re_resolved=re_resolved,
        )

    def _diagnose_unavailable(
        self,
        query: AXElementQuery,
        scoped: list[AXElementSnapshot],
        now: datetime,
        require_enabled: bool,
    ) -> str:
        potential = [element for element in scoped if _potential_match(query, element)]
        if potential and all(not self._is_fresh(element, now) for element in potential):
            return "matching AX observation is stale and must be re-inspected"
        fresh = [element for element in potential if self._is_fresh(element, now)]
        if fresh and all(element.visible is False for element in fresh):
            return "matching AX element is not visible and must be re-resolved"
        visible = [element for element in fresh if element.visible is not False]
        if require_enabled and visible and all(element.enabled is not True for element in visible):
            return "matching AX element is disabled"
        return "semantic AX element not found"

    @staticmethod
    def _reject(
        reason: str,
        freshness: datetime,
        re_resolved: bool = False,
    ) -> AXResolutionResult:
        return AXResolutionResult(
            confidence=0,
            candidate_count=0,
            ambiguous=False,
            rejection_reason=reason,
            freshness_timestamp=freshness,
            re_resolved=re_resolved,
        )


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())


def _potential_match(query: AXElementQuery, element: AXElementSnapshot) -> bool:
    if query.identifier is not None:
        return element.identifier == query.identifier
    if query.role is not None and query.label is not None:
        return element.role == query.role and _normalize(element.label or "") == _normalize(
            query.label
        )
    if query.parent_path:
        return element.parent_path == query.parent_path
    return False
