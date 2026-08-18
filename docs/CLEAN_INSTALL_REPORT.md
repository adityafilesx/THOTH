# OmniMac clean-install report

**Date:** 2026-07-14  
**Outcome:** failed release gate; no installable complete product bundle

Tauri produced a 9.5 MB `OmniMac.app` and 2.9 MB DMG. Inspection showed only the
desktop executable, icon, and plist. The bundle does not contain or install the
Python daemon, AX helper, whisper.cpp runtime, Whisper model, local-model setup,
launch agent, onboarding, upgrade logic, or uninstall/data-removal workflow.
Its bundle identifier/version remain `dev.omnimac.desktop` / `0.1.0`, and the
plist has no microphone usage description.

The artifact was therefore not installed into another macOS account and is not
a valid clean-install candidate. The developer checkout cannot substitute for
a clean account or machine. First-run permissions, menu presence, push-to-talk,
planner/TTS/Stop, relaunch, login launch, upgrade identity/config retention,
uninstall, orphan cleanup, secret-log inspection, and data removal remain
unverified for an installed build.

This is a distribution blocker. Fixing it would require packaging/onboarding
work beyond this validation-only run, so no new installer capability was added.

