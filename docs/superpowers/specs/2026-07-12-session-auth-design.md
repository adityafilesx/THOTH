# Slice 2 — Desktop↔daemon session auth token (design/spec)

**Date:** 2026-07-12 · **Phase:** 3 · **Status:** approved design, pre-plan
**Depends on:** Phase 2 core; slice 1 (scope enforcement) merged.
**Blocks:** every real mutating capability (slice 3+) — those must never be reachable by an unauthenticated local process.

## 1. Context & problem

The daemon binds `127.0.0.1` but requires **no authentication** (threat **T6**, accepted residual risk for Phases 0–2). While all tools are in-memory mocks this is tolerable. The moment a real filesystem/shell/app tool lands (slice 3), any local process that can reach `127.0.0.1:7710` can drive the real computer — RCE-equivalent. This slice adds a per-session bearer token that the desktop presents on every call; the daemon rejects everything else. **No real I/O ships here.**

## 2. Goals / non-goals

**Goals**
- A per-session token minted by the daemon, handed to the desktop over a user-only (0600) file.
- HTTP guard (bearer, constant-time compare) on every endpoint except the liveness probe.
- WebSocket guard via a first-message handshake (browser `WebSocket` cannot set headers).
- Desktop client attaches the token to HTTP + WS; Tauri shell reads the token file via its first custom command.
- Auth is **always on** — no runtime flag that could ship it disabled. The test suite authenticates like the real client.
- Full TDD; existing 290 daemon + 42 desktop tests stay green (after fixtures authenticate).

**Non-goals (this slice)**
- Any real file/shell/app/browser I/O (slice 3+).
- Permissions/Skills/Settings view wiring (slice 9).
- Token rotation / expiry mid-session (one token per daemon process is sufficient for the local-IPC threat; revisit only if a requirement appears).
- TLS on localhost (out of scope; the threat is other local processes, addressed by the secret token + loopback bind).

## 3. Components (new & touched)

| File | New? | Responsibility |
|---|---|---|
| `apps/daemon/src/thoth_daemon/security/auth.py` | new | `mint_token()`, `write_token_file(path, token)` (0600), `token_matches(a, b)` (constant-time). |
| `apps/daemon/src/thoth_daemon/api/middleware.py` | new | `require_bearer` HTTP middleware: 401 unless `Authorization: Bearer <token>`; exempts `/api/health`. |
| `apps/daemon/src/thoth_daemon/api/ws.py` | edit | First-message auth handshake before streaming; close 1008 on failure. |
| `apps/daemon/src/thoth_daemon/config.py` | edit | `session_token: str \| None = None`, `session_token_path: Path = data/session.token`. |
| `apps/daemon/src/thoth_daemon/app.py` | edit | Resolve token (env or mint), store on `app.state.session_token`, write file, register middleware. |
| `apps/daemon/tests/conftest.py` | edit | Test settings set a fixed token; `client`/`ws_client` authenticate. |
| `apps/desktop/src-tauri/src/lib.rs` | edit | `session_token()` command reads the token file; register via `invoke_handler`. |
| `apps/desktop/src-tauri/tauri.conf.json` | edit (if needed) | Allow the command / fs read of the token path. |
| `apps/desktop/src/lib/auth.ts` | new | `getSessionToken()` — Tauri `invoke` else `VITE_THOTH_TOKEN`; in-memory cache. |
| `apps/desktop/src/lib/api.ts` | edit | Attach `Authorization: Bearer` to every request. |
| `apps/desktop/src/lib/ws.ts` | edit | Send `{type:"auth", token}` on open; then proceed. |
| `apps/desktop/src/main.tsx` (bootstrap) | edit | Fetch token before first connect. |
| `docs/DECISIONS.md`, `docs/THREAT_MODEL.md`, `docs/STATUS.md`, `docs/MILESTONES.md` | edit | ADR, T6 mitigation, truthful status. |

## 4. Token lifecycle

1. **Mint / source.** At startup `app.py` sets `token = cfg.session_token or mint_token()`. `mint_token()` = `secrets.token_urlsafe(32)`. Env `THOTH_SESSION_TOKEN` (via `cfg.session_token`) lets dev/tests pin a value.
2. **Store.** `app.state.session_token = token`. Never written to SQLite; redaction masks `token`/`authorization` keys in logs/audit already.
3. **Handoff.** `write_token_file(cfg.session_token_path, token)` writes the raw token with mode **0600** (create parent dir if needed). This is the desktop's read channel.
4. **Present.** Desktop reads the file (Tauri) or env (dev) and sends it on every HTTP/WS call.

## 5. HTTP guard (`api/middleware.py`)

Registered with `@app.middleware("http")` (HTTP only; never sees the WS scope). For each request:
- If `request.url.path == "/api/health"` → pass through (liveness must work pre-auth).
- Else read `Authorization`; require `Bearer <token>` where `token_matches(provided, request.app.state.session_token)` using `secrets.compare_digest`.
- On missing/malformed/mismatch → `JSONResponse(status_code=401, {"detail": "unauthorized"})`; do **not** call the route.

`/api/health` stays open by design (standard liveness; reveals only version + db status). Everything else — tasks, approvals, permissions, workspaces, audit — is guarded.

## 6. WebSocket guard (`api/ws.py`)

Browser `WebSocket` can't send headers, so:
- `await websocket.accept()`.
- `frame = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)`; require `frame.get("token")` matches via `token_matches`.
- On timeout / bad / absent → `await websocket.close(code=1008)` and return **before** subscribing to the bus or sending any event.
- On success → send `connection.established`, then stream as today.

## 7. Desktop client

- **`auth.ts`:** `getSessionToken(): Promise<string \| null>` — when running under Tauri (feature-detect the Tauri global injected into `window`; exact key confirmed against the installed `@tauri-apps/api` in the plan), `invoke<string>("session_token")`; else `import.meta.env.VITE_THOTH_TOKEN ?? null`. Cache the resolved value in a module variable (memory only — never `localStorage`).
- **`api.ts`:** `request()` awaits `getSessionToken()` and adds `Authorization: Bearer <token>` when present (alongside `Content-Type`).
- **`ws.ts`:** in `open()`, on `onopen` send `JSON.stringify({ type: "auth", token })` before marking connected; the server replies `connection.established`.
- **Rust `session_token()`:** reads `THOTH_SESSION_TOKEN` env if set, else the token file (path from `THOTH_SESSION_TOKEN_PATH` or the default under the app data dir); returns `Option<String>`. Registered via `.invoke_handler(tauri::generate_handler![session_token])`. Updates the "no custom commands" comment — this is the reviewed capability.

## 8. Error handling

| Situation | Result |
|---|---|
| HTTP no/blank Authorization | 401 `unauthorized` |
| HTTP wrong token | 401 (constant-time compare) |
| HTTP to `/api/health` | 200, no auth |
| WS no first frame within 5 s | close 1008 |
| WS wrong/absent token | close 1008, no stream |
| Desktop token unavailable | requests go out unauthenticated → 401; surfaced as a connection error (no crash) |

## 9. Testing strategy (TDD)

- **`security/auth.py`:** `mint_token` length/uniqueness; `write_token_file` creates a 0600 file with exact contents; `token_matches` true/false and rejects length-mismatch safely.
- **HTTP guard:** every protected route returns 401 without a token and with a wrong token; 200 with the right token; `/api/health` 200 without a token. Driven through the real ASGI app.
- **WS guard:** connect + send correct auth frame → receives `connection.established` + events; connect + wrong token → closed, no events; connect + no frame → closed after timeout.
- **conftest:** `settings` fixture sets `session_token="test-token"` **and `session_token_path=tmp_path/"session.token"`** (so tests never write into the repo `./data`); `client` fixture attaches `Authorization: Bearer test-token`; WS tests send the auth frame first. This keeps all 290 existing tests green while proving auth is enforced.
- **Desktop (vitest):** `request()` includes the header when `getSessionToken` resolves a token; `WsClient` sends the auth frame on open (mock `WebSocket`); `getSessionToken` falls back to `VITE_THOTH_TOKEN` when Tauri is absent.
- **Manual (Rust):** the `session_token()` command is verified by a live `make dev` smoke test (documented) — Rust command unit-testing is out of proportion for a 10-line file reader; its behavior is exercised end-to-end.

## 10. Preserved invariants

No execution outside EXECUTING; no risk downgrade; scope enforcement (slice 1) unchanged; append-only audit; redaction at every boundary (now covering the token). Auth is always on (no disable flag). No capability overclaim — still no real I/O.

## 11. ADR + threat model

- **ADR-012:** per-session bearer token; file handoff (0600); HTTP middleware + WS handshake; constant-time compare; auth always-on. Rejected: query-param WS token (URL logging), OS-keychain handoff (heavier; the token is ephemeral per-session), a disable flag (ship-off risk).
- **ADR-013 (or in ADR-012):** deliberate scoped exception to "no secrets in frontend state" — the session token is IPC auth material, held in memory only, never persisted by the frontend, redacted from logs/audit.
- **THREAT_MODEL:** T6 mitigation row updated from "planned" to implemented; residual-risk bullet updated.
