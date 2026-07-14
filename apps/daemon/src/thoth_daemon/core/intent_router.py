"""Reflex / skill / local-reasoning intent router (Phase 5 slice 3).

Not every request goes through an LLM. The router classifies an incoming
text (typed or transcribed) into one of three tiers:

- REFLEX — deterministic commands (stop, cancel, status, open/focus an
  APPROVED app, run a KNOWN skill, continue a KNOWN workspace, mute,
  interrupt). Pure pattern matching; NO inference provider is ever
  constructed or called.
- SKILL — reserved for installed workflows resolved deterministically
  (the RUN_SKILL reflex covers the common case; richer input extraction
  belongs to the planner tier).
- PLANNER — novel or ambiguous requests; the ONLY tier that may touch an
  inference provider (the local constrained planner, slice 4).

Reflex matching is anchored (exact / prefix / explicit verb + argument),
never arbitrary substring, so a sentence that merely CONTAINS "stop" is
not forged into a reflex. All reflex actions are themselves safe
(stop/cancel/status/mute) or scope-gated (open only APPROVED apps); a
hostile string cannot use this path to bypass a gate, and there is no
"approve" reflex at all.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class RouteTier(StrEnum):
    REFLEX = "reflex"
    SKILL = "skill"
    PLANNER = "planner"
    CLARIFY = "clarify"


class ReflexKind(StrEnum):
    STOP = "stop"
    CANCEL = "cancel"
    STATUS = "status"
    OPEN_APP = "open_app"
    FOCUS_APP = "focus_app"
    RUN_SKILL = "run_skill"
    CONTINUE_WORKSPACE = "continue_workspace"
    MUTE = "mute"
    INTERRUPT = "interrupt"


class RoutedIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: RouteTier
    raw: str
    reflex_kind: ReflexKind | None = None
    target: str | None = None
    skill_inputs: dict[str, str] = Field(default_factory=dict)
    planner_goal: str | None = None
    clarification: str | None = None


_WORD = r"[A-Za-z0-9 ._-]"

# Bare commands: the WHOLE (normalized) utterance is the command, optionally
# wrapped with the wake word "thoth" and trivial politeness.
_BARE = [
    (ReflexKind.STOP, re.compile(r"^(thoth[ ,]*)?stop( thoth)?[.! ]*$")),
    (ReflexKind.CANCEL, re.compile(r"^(thoth[ ,]*)?cancel( (the |this |that ?))?(task)?[.! ]*$")),
    (
        ReflexKind.STATUS,
        re.compile(r"^(what('| i)?s )?(the )?(current )?(task )?status[?.! ]*$"),
    ),
    (
        ReflexKind.STATUS,
        re.compile(r"^read (the )?(current )?(task )?status[?.! ]*$"),
    ),
    (
        ReflexKind.STATUS,
        re.compile(r"^what am i working on[?.! ]*$"),
    ),
    (ReflexKind.MUTE, re.compile(r"^(thoth[ ,]*)?mute( thoth| yourself)?[.! ]*$")),
    (
        ReflexKind.INTERRUPT,
        re.compile(r"^(thoth[ ,]*)?(interrupt|be quiet|quiet|hush|stop speaking)( thoth)?[.! ]*$"),
    ),
]

# Verb + argument commands. The argument must resolve against a known set.
_OPEN = re.compile(rf"^(open|launch)\s+(?P<arg>{_WORD}+?)[.! ]*$")
_FOCUS = re.compile(rf"^(focus|switch to|bring up|go to)\s+(?P<arg>{_WORD}+?)[.! ]*$")
_BRING_FORWARD = re.compile(rf"^bring\s+(?P<arg>{_WORD}+?)\s+forward[.! ]*$")
_RUN = re.compile(rf"^(run|start|execute)\s+(the\s+)?(?P<arg>{_WORD}+?)( skill)?[.! ]*$")
_CONTINUE = re.compile(rf"^continue\s+(the\s+)?(?P<arg>{_WORD}+?)( workspace| project)?[.! ]*$")


class IntentRouter:
    def __init__(
        self,
        known_apps: set[str],
        known_skills: set[str],
        known_workspaces: set[str],
        skill_aliases: dict[str, str] | None = None,
    ) -> None:
        self._apps = {a.lower(): a for a in known_apps}
        self._skills = {s.lower(): s for s in known_skills}
        self._workspaces = {w.lower(): w for w in known_workspaces}
        self._skill_aliases = {k.lower(): v for k, v in (skill_aliases or {}).items()}

    def route(self, text: str) -> RoutedIntent:
        norm = " ".join(text.strip().split())
        low = norm.lower()
        command = re.sub(r"^thoth(?:[ ,]+)", "", low)

        for kind, rx in _BARE:
            if rx.match(low) or rx.match(command):
                return RoutedIntent(tier=RouteTier.REFLEX, reflex_kind=kind, raw=text)

        if skill := self._resolve_skill(command.rstrip(".!? ")):
            return RoutedIntent(
                tier=RouteTier.REFLEX,
                reflex_kind=ReflexKind.RUN_SKILL,
                target=skill,
                raw=text,
            )

        m = _OPEN.match(command)
        if m and (app := self._apps.get(m.group("arg").strip())):
            return RoutedIntent(
                tier=RouteTier.REFLEX, reflex_kind=ReflexKind.OPEN_APP, target=app, raw=text
            )

        m = _FOCUS.match(command) or _BRING_FORWARD.match(command)
        if m and (app := self._apps.get(m.group("arg").strip())):
            return RoutedIntent(
                tier=RouteTier.REFLEX, reflex_kind=ReflexKind.FOCUS_APP, target=app, raw=text
            )

        m = _RUN.match(command)
        if m and (skill := self._resolve_skill(m.group("arg").strip())):
            return RoutedIntent(
                tier=RouteTier.REFLEX, reflex_kind=ReflexKind.RUN_SKILL, target=skill, raw=text
            )

        m = _CONTINUE.match(command)
        if m and (ws := self._workspaces.get(m.group("arg").strip())):
            return RoutedIntent(
                tier=RouteTier.REFLEX,
                reflex_kind=ReflexKind.CONTINUE_WORKSPACE,
                target=ws,
                raw=text,
            )

        # Everything else is novel/ambiguous → the local planner tier.
        return RoutedIntent(tier=RouteTier.PLANNER, planner_goal=norm, raw=text)

    def _resolve_skill(self, arg: str) -> str | None:
        if arg in self._skills:
            return self._skills[arg]
        return self._skill_aliases.get(arg)


_NATURAL_SKILL_ALIASES: dict[str, str] = {
    "run the tests": "run-project-tests",
    "run tests": "run-project-tests",
    "prepare a commit": "prepare-git-commit",
    "show the modified files": "project-health-check",
    "show modified files": "project-health-check",
    "summarize the workspace": "organize-workspace",
    "summarise the workspace": "organize-workspace",
}


def build_skill_aliases(skill_names: set[str]) -> dict[str, str]:
    aliases = {name.replace("-", " "): name for name in skill_names}
    aliases.update(
        {
            phrase: target
            for phrase, target in _NATURAL_SKILL_ALIASES.items()
            if target in skill_names
        }
    )
    return aliases


class IntentPlanner(Protocol):
    async def plan_intent(self, goal: str) -> object: ...


async def dispatch_intent(router: IntentRouter, text: str, planner: IntentPlanner) -> RoutedIntent:
    """Route, and invoke the planner ONLY for the planner tier. Reflex and
    skill intents are returned without ever touching the provider — this is
    the enforced 'no LLM on the reflex path' guarantee."""
    intent = router.route(text)
    if intent.tier is RouteTier.PLANNER and intent.planner_goal is not None:
        await planner.plan_intent(intent.planner_goal)
    return intent
