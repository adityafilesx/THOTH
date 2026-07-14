# Phase 5.4 TCC closure

**Date:** 2026-07-14
**Outcome:** host identity closed; real AX workflow evidence still open

The unstable Python TCC identity has been replaced by the local-only helper
`me.adityalabs.thoth.axhelper`. The release build compiles, packages, verifies
its code signature, launches as a background app, creates a user-owned
mode-0600 Unix socket, authenticates peer UID, and answers a live trust probe.
The probe returned `false`, which is the correct current result.

Automated helper and semantic-AX regression coverage passes. The daemon has no
silent Python fallback. Settings may be opened only through the existing
literal user-request endpoint; THOTH cannot grant or toggle Accessibility.

The required real fixture, delayed/ambiguous/moving element, modal, TextEdit
exact-readback, VS Code final-focus, and manual revocation capstones remain
unverified because the exact helper is not TCC-trusted and the desktop remains
at `com.apple.loginwindow`. No application capability was promoted. Phase 5.4
implementation is complete, but its required real evidence is partially open.
