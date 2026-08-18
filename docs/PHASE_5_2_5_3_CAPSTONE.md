# Phase 5.2–5.3 capstone evidence

**Date:** 2026-07-13; unlocked-focus addendum 2026-07-14

**Branch:** `phase-5/persona`

**Environment:** Apple M4 Mac, 16 GB unified memory; host context used for NSWorkspace, Chromium, sockets, `sysctl`, and loopback Ollama.

## Automated gate

- Daemon: **782 passed, 1 skipped**.
- Desktop: **65 passed**.
- Total passing: **847**.
- Ruff check/format, strict mypy, ESLint, TypeScript, Vite build, Cargo check, and fresh Alembic upgrade: passed.
- Exact `make test`: passed.

The original run had one skip because the interactive desktop was locked and
`com.apple.loginwindow` was frontmost. On 2026-07-14 the unlocked rerun
collected all six foreground/focus live tests without a skip. A separate exact
Code → TextEdit action → Code restoration sequence reported
`restored=True`, `verified=True`, and independently probed final bundle id
`com.microsoft.VSCode`.

## Required capstones

| # | Capstone | Outcome | Evidence / limitation |
|---|---|---|---|
| 1 | Detect actual foreground application | Pass | Original host probe returned `loginwindow`; unlocked addendum returned ChatGPT / `com.openai.codex`. |
| 2 | Detect Finder when foreground | Not verified | Finder was detected running; foreground transition was blocked by the locked desktop. |
| 3 | Detect TextEdit when foreground | Not verified | TextEdit launched and was detected running; `loginwindow` remained frontmost. |
| 4 | Detect VS Code | Pass | Real `Code` / `com.microsoft.VSCode` process detected. |
| 5 | Match OmniMac workspace in VS Code | Pass, bounded | Real Code bundle plus authoritative approved OmniMac path/task workspace matched; no title-only authority. |
| 6 | Open TextEdit and leave focused | Failed closed | Launch succeeded; final focus could not be verified while locked. |
| 7 | Start background service without focus theft | Pass | Real loopback Python HTTP service ran; frontmost bundle remained `loginwindow`; service terminated. |
| 8 | Temporarily focus app and restore original | Pass on unlocked rerun | Started with Code / `com.microsoft.VSCode`; invoked temporary TextEdit focus under `RESTORE_PREVIOUS_FOCUS`; final NSWorkspace probe was Code / `com.microsoft.VSCode`; result was restored and verified. |
| 9 | Resolve “open it” for one recent artifact | Pass | Real temporary artifact, authoritative same-task reference. |
| 10 | Reject ambiguous “open it” | Pass | Two real artifacts raise `DialogueAmbiguous`. |
| 11 | Expire dialogue and reject stale reference | Pass | Expired state is removed and raises `DialogueExpired`. |
| 12 | Local model unavailable → deterministic degraded response | Pass | Model-dependent failure maps to deterministic `degraded_mode`; host-context live Qwen tests also passed. |
| 13 | Real partial-completion response | Pass | Live task API: draft-read verified, send approval denied, response was `partial_completion`. |
| 14 | No continuous screenshots stored | Pass | Broker is on-demand; schema/history contain no screenshot/image field. |
| 15 | No full Accessibility tree retained | Pass | Foreground schema/history contain no AX-tree field; AX remains permission-gated. |

## Security/adversarial results

- Model false success, target substitution, invented counts, tool-shaped persona output, approval pressure, and risk directives are rejected or fall back deterministically.
- Window-title injection and workspace-title spoofing cannot grant scope; sensitive titles/paths redact before retention/log labeling.
- Dialogue cannot replay approval, cross tasks, select unapproved workspaces, or bypass `no_push`.
- Capability profiles cannot self-expand or downgrade forbidden operations.
- Unapproved app focus is stopped by scope; ambiguous focus runs nothing; disappearing restoration targets, cancellation, and background focus theft are detected.
- Focus/tool imports succeed in either order in fresh interpreters.

## Unlocked-focus addendum

Executed on 2026-07-14:

```bash
uv run --project apps/daemon pytest \
  apps/daemon/tests/core/test_foreground_live.py \
  apps/daemon/tests/core/test_focus_live.py -v -s
```

Result: **6 passed**. The three inventory checks, actual-frontmost capture,
temporary restoration test, and background-service focus-preservation test all
passed. Direct Finder-frontmost and TextEdit-leave-focused capstones remain
separate Phase 5.4 evidence items; this addendum does not infer them from
process inventory.
