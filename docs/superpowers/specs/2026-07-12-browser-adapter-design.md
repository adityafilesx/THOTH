# Slice 7 — Browser adapter with domain allowlist (design/spec)

**Date:** 2026-07-12 · **Phase:** 3 · **Status:** building (Stop-hook-driven) · **Verifiable here:** YES (Playwright + headless Chromium confirmed working).

## 1. Decision: Playwright-Python behind a `BrowserAdapter` interface (not the Node MCP server)

The goal names "Playwright MCP". For a Python daemon, Playwright-Python gives the same capability +
domain allowlist **without** an extra Node process and an MCP-client layer, and it is **verifiable
now** (confirmed: chromium installs + renders + reads text). The engine sits behind a
`BrowserAdapter` protocol, so a real MCP-server-backed adapter could be swapped in later behind the
same interface with zero change to tools or the safety contract. Recorded as **ADR-018**.

## 2. Scope

One tool, `browser_read` (R1): navigate to a URL and return its visible text + title. **Domain
allowlist is enforced by the slice-1 scope enforcer** — `requested_scope(domains=[host])`, so the
URL's hostname must be in the workspace's `approved_domains` (empty by default → denied). Only
`http`/`https`. Page text is untrusted web content → a redaction field (never persisted). No
clicking/forms/downloads/JS-eval this slice.

## 3. Components

| File | New? | Responsibility |
|---|---|---|
| `pyproject.toml` | edit | add `playwright>=1.47`; browsers install via `playwright install chromium` (documented in setup). |
| `browser/__init__.py`, `browser/browser_adapter.py` | new | `PageContent`, `BrowserAdapter` protocol, `PlaywrightBrowser` (lazy import, headless chromium, launch-per-call = stateless), `MockBrowser`, `default_browser()`. |
| `tools/browser_tools.py` | new | `BrowserRead` (R1, OUTPUT_ASSERTION, `redaction_fields=["text"]`, `timeout_s=30`) + `register_browser_tools`. |
| `app.py` | edit | `register_browser_tools(registry)`. |
| docs | edit | ADR-018, STATUS, MILESTONES, THREAT_MODEL. |

## 4. Behavior

- `requested_scope`: `host = urlparse(url).hostname or ""` → `ResourceScope(domains=[host])`. Enforcer
  refuses a host not in `approved_domains` (exact, case-insensitive; subdomain matching deferred).
- `run`: reject non-`http(s)` scheme (raise). `dry_run` → no navigation. Else `adapter.fetch(url,
  timeout)`: launch headless chromium, `goto(url, wait_until="domcontentloaded")`, read `title` +
  `inner_text("body")`, cap 64 KiB, close browser (finally). Cancellation/timeout: the registry's
  outer `wait_for` cancels `run`; the `async with async_playwright()` / `finally: browser.close()`
  tears the browser down — no orphan.
- Web text is redacted in audit/logs/WS (`redaction_fields=["text"]`); returned in-process for later
  use. Its provenance is `WEB_UNTRUSTED` — the injection guard applies when it reaches the planner.

## 5. Testing / verification

- **Unit (MockBrowser):** read returns title/text; unknown page → failure; non-http scheme → failure;
  dry-run no navigation; `requested_scope(domains=[host])`; data:/no-host URL → empty-host scope.
- **Scope (backstop):** `browser_read` of a host not in `allowed.domains` → `scope violation`; in-scope
  (mock) ok with `text` masked in output.
- **Real Playwright (guarded — skip if chromium can't launch):** `PlaywrightBrowser().fetch` on a
  `data:text/html,...` URL (no network) returns the rendered text — verifies the real engine, fast.
- **Live smoke (script):** through the registry, `browser_read` a real allowed `https` host → real
  title/text; a non-allowed host → refused by scope.

## 6. Honesty

Real browser read is OS-verified. Still not autonomous control (no planner). No clicking/forms yet.

## 7. ADR-018

Playwright-Python behind `BrowserAdapter` (MCP-swappable); domain allowlist via
`requested_scope(domains=)` + the slice-1 enforcer; text redacted + `WEB_UNTRUSTED`; read-only, no
interaction. Deviation from the goal's "Playwright MCP" justified by: Python-native, no extra
process, verifiable now, same safety contract, interface-swappable.
