# Session Auth Token Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A per-session bearer token gates every daemon call (HTTP + WebSocket), handed to the desktop over a 0600 file / dev env, closing threat T6 before real capabilities land.

**Architecture:** Daemon mints (or reads from env) a token at startup, stores it on `app.state`, writes it 0600. An HTTP middleware requires `Authorization: Bearer <token>` (constant-time compare) on all routes except `/api/health`; the WS endpoint requires a first-message auth frame. The desktop attaches the token from a Tauri command (packaged) or `VITE_OmniMac_TOKEN` (dev). Auth is always on.

**Tech Stack:** Python 3.12/FastAPI/Starlette, Rust/Tauri 2, TypeScript/vitest.

## Global Constraints

- Auth is **always on** — no runtime disable flag. The test suite authenticates like the real client.
- `mypy --strict` + ruff clean; TS `tsc --noEmit` + eslint clean. All boundary models `extra="forbid"`.
- Existing 290 daemon + 42 desktop tests stay green after fixtures authenticate.
- Constant-time token compare (`secrets.compare_digest`). Token never in SQLite; redaction already masks `token`/`authorization` keys.
- `/api/health` stays unauthenticated (liveness).
- Branch `phase-3/session-auth`. Every commit ends with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` (second `-m`). No push.
- No real I/O; STATUS keeps "OmniMac cannot control the computer".

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `apps/daemon/src/omnimac_daemon/security/auth.py` | Create | `mint_token`, `write_token_file` (0600), `token_matches` (constant-time). |
| `apps/daemon/src/omnimac_daemon/api/middleware.py` | Create | `require_bearer` HTTP middleware. |
| `apps/daemon/src/omnimac_daemon/config.py` | Modify | `session_token`, `session_token_path`. |
| `apps/daemon/src/omnimac_daemon/app.py` | Modify | Resolve/store/write token; register middleware. |
| `apps/daemon/src/omnimac_daemon/api/ws.py` | Modify | First-message auth handshake. |
| `apps/daemon/tests/conftest.py` | Modify | Test token + authenticated `client`. |
| `apps/desktop/src/lib/auth.ts` | Create | `getSessionToken` (Tauri invoke / dev env). |
| `apps/desktop/src/lib/api.ts` | Modify | Attach bearer header. |
| `apps/desktop/src/lib/ws.ts` | Modify | Send auth frame on open. |
| `apps/desktop/src-tauri/src/lib.rs` | Modify | `session_token()` command. |
| `Makefile` | Modify | Shared `DEV_TOKEN` for `daemon` + `desktop`. |
| `docs/DECISIONS.md`, `docs/THREAT_MODEL.md`, `docs/STATUS.md`, `docs/MILESTONES.md` | Modify | ADR, T6 mitigation, status. |

Tests: `tests/security/test_auth.py`, `tests/api/test_auth_http.py`, `tests/api/test_ws.py` + `test_ws_tasks.py` (edit), `apps/desktop/src/lib/auth.test.ts`, `api.test.ts`, `ws.test.ts`.

---

### Task 1: Token primitives (`security/auth.py`)

**Files:**
- Create: `apps/daemon/src/omnimac_daemon/security/auth.py`
- Test: `apps/daemon/tests/security/test_auth.py`

**Interfaces:**
- Produces: `mint_token() -> str`; `write_token_file(path: Path, token: str) -> None`; `token_matches(provided: str | None, expected: str | None) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# apps/daemon/tests/security/test_auth.py
import stat
from pathlib import Path

from omnimac_daemon.security.auth import mint_token, token_matches, write_token_file


def test_mint_token_is_long_and_unique() -> None:
    a, b = mint_token(), mint_token()
    assert len(a) >= 32 and a != b


def test_write_token_file_is_0600_with_exact_contents(tmp_path: Path) -> None:
    p = tmp_path / "sub" / "session.token"
    write_token_file(p, "abc123")
    assert p.read_text() == "abc123"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_write_token_file_tightens_existing_perms(tmp_path: Path) -> None:
    p = tmp_path / "session.token"
    p.write_text("old")
    p.chmod(0o644)
    write_token_file(p, "new")
    assert p.read_text() == "new"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_token_matches() -> None:
    assert token_matches("s3cret", "s3cret")
    assert not token_matches("s3cret", "other")
    assert not token_matches(None, "s3cret")
    assert not token_matches("s3cret", None)
    assert not token_matches("", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/security/test_auth.py -q`
Expected: FAIL — `ModuleNotFoundError: omnimac_daemon.security.auth`.

- [ ] **Step 3: Write minimal implementation**

```python
# apps/daemon/src/omnimac_daemon/security/auth.py
"""Session auth primitives.

A per-session bearer token authenticates the desktop to the daemon,
mitigating threat T6 (other local processes reaching the loopback API).
The token is IPC auth material — held in memory, written 0600 for handoff,
never persisted to SQLite, and redacted from logs/audit."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def mint_token() -> str:
    return secrets.token_urlsafe(32)


def write_token_file(path: Path, token: str) -> None:
    """Write *token* to *path* with 0600 permissions, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, token.encode())
    finally:
        os.close(fd)
    os.chmod(path, 0o600)  # tighten even if the file pre-existed


def token_matches(provided: str | None, expected: str | None) -> bool:
    """Constant-time comparison that tolerates None/empty without leaking."""
    if not provided or not expected:
        return False
    return secrets.compare_digest(provided, expected)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/security/test_auth.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/daemon/src/omnimac_daemon/security/auth.py apps/daemon/tests/security/test_auth.py
git commit -m "feat(security): session token primitives (mint, 0600 write, constant-time compare)" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: HTTP guard (middleware + config + app + conftest)

**Files:**
- Create: `apps/daemon/src/omnimac_daemon/api/middleware.py`
- Modify: `apps/daemon/src/omnimac_daemon/config.py`, `apps/daemon/src/omnimac_daemon/app.py`, `apps/daemon/tests/conftest.py`
- Test: `apps/daemon/tests/api/test_auth_http.py`

**Interfaces:**
- Consumes: `token_matches` (Task 1).
- Produces: `require_bearer(request, call_next)` middleware; `app.state.session_token`; `Settings.session_token`, `Settings.session_token_path`.

- [ ] **Step 1: Write the failing test**

```python
# apps/daemon/tests/api/test_auth_http.py
from httpx import AsyncClient


async def test_health_is_open_without_token(client: AsyncClient) -> None:
    # client sends a valid token, but health must not require it — prove by
    # sending an explicitly bad header.
    r = await client.get("/api/health", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 200


async def test_protected_route_rejects_missing_token(client: AsyncClient) -> None:
    r = await client.get("/api/tasks", headers={"Authorization": ""})
    assert r.status_code == 401


async def test_protected_route_rejects_wrong_token(client: AsyncClient) -> None:
    r = await client.get("/api/tasks", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


async def test_protected_route_accepts_valid_token(client: AsyncClient) -> None:
    # client fixture attaches the valid bearer by default.
    r = await client.get("/api/tasks")
    assert r.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/api/test_auth_http.py -q`
Expected: FAIL — missing/blank token currently returns 200 (no auth yet); `session_token` unknown to Settings.

- [ ] **Step 3a: Config fields**

In `apps/daemon/src/omnimac_daemon/config.py`, add after `planner`:

```python
    session_token: str | None = None
    session_token_path: Path = Path("./data/session.token")
```

- [ ] **Step 3b: Middleware**

```python
# apps/daemon/src/omnimac_daemon/api/middleware.py
"""HTTP auth middleware — every request needs the session bearer token
except the liveness probe. WebSocket auth is handled in api/ws.py."""

from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from omnimac_daemon.security.auth import token_matches

_OPEN_PATHS = frozenset({"/api/health"})


async def require_bearer(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    if request.url.path in _OPEN_PATHS:
        return await call_next(request)
    expected = getattr(request.app.state, "session_token", None)
    header = request.headers.get("Authorization", "")
    provided = header[7:] if header.startswith("Bearer ") else None
    if not token_matches(provided, expected):
        return JSONResponse(status_code=401, content={"detail": "unauthorized"})
    return await call_next(request)
```

- [ ] **Step 3c: Wire app.py**

Add imports:

```python
from omnimac_daemon.api.middleware import require_bearer
from omnimac_daemon.security.auth import mint_token, write_token_file
```

In `lifespan`, after `bus = EventBus()` and before building the orchestrator, resolve the token:

```python
        token = cfg.session_token or mint_token()
        app.state.session_token = token
        write_token_file(cfg.session_token_path, token)
```

In `create_app`, register the middleware right after `app = FastAPI(...)`:

```python
    app.middleware("http")(require_bearer)
```

- [ ] **Step 3d: Authenticate the test client**

In `apps/daemon/tests/conftest.py`, extend the `settings` fixture:

```python
    return Settings(
        db_path=tmp_path / "test.db",
        log_dir=tmp_path / "logs",
        trusted_workspaces=[str(tmp_path / "trusted")],
        approval_ttl_seconds=60,
        session_token="test-token",
        session_token_path=tmp_path / "session.token",
    )
```

and give the `client` fixture a default bearer header:

```python
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": "Bearer test-token"},
        ) as c:
            yield c
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/api -q`
Expected: PASS — new auth tests pass; every existing HTTP API test still passes (client now authenticates). WS tests are unaffected (middleware is HTTP-only).

- [ ] **Step 5: Commit**

```bash
git add apps/daemon/src/omnimac_daemon/api/middleware.py apps/daemon/src/omnimac_daemon/config.py \
        apps/daemon/src/omnimac_daemon/app.py apps/daemon/tests/conftest.py \
        apps/daemon/tests/api/test_auth_http.py
git commit -m "feat(api): bearer-token HTTP middleware; mint+write session token at startup" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: WebSocket auth handshake

**Files:**
- Modify: `apps/daemon/src/omnimac_daemon/api/ws.py`, `apps/daemon/tests/api/test_ws.py`, `apps/daemon/tests/api/test_ws_tasks.py`

**Interfaces:**
- Consumes: `token_matches` (Task 1); `app.state.session_token` (Task 2).
- Produces: `/ws` requires a first frame `{"type":"auth","token":<token>}` before streaming.

- [ ] **Step 1: Write the failing test** (new cases in `test_ws.py`)

Add to `apps/daemon/tests/api/test_ws.py`:

```python
def test_ws_rejects_wrong_token(ws_client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with ws_client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": "wrong"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_ws_rejects_missing_auth_frame(ws_client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with ws_client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "not-auth"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
```

Add `import pytest` at the top of `test_ws.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/api/test_ws.py -q`
Expected: FAIL — server currently sends `connection.established` without auth, so no disconnect occurs.

- [ ] **Step 3a: Add the handshake**

Replace `apps/daemon/src/omnimac_daemon/api/ws.py` with:

```python
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from omnimac_daemon.events.bus import EventBus
from omnimac_daemon.security.auth import token_matches

router = APIRouter()

_AUTH_TIMEOUT_S = 5.0


@router.websocket("/ws")
async def event_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    expected = getattr(websocket.app.state, "session_token", None)
    try:
        frame = await asyncio.wait_for(websocket.receive_json(), timeout=_AUTH_TIMEOUT_S)
    except (TimeoutError, WebSocketDisconnect, ValueError):
        await websocket.close(code=1008)
        return
    provided = frame.get("token") if isinstance(frame, dict) else None
    if not token_matches(provided, expected):
        await websocket.close(code=1008)
        return

    bus: EventBus = websocket.app.state.bus
    queue = bus.subscribe()
    try:
        await websocket.send_json({"type": "connection.established", "payload": {}})
        while True:
            envelope = await queue.get()
            await websocket.send_json(envelope)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)
```

- [ ] **Step 3b: Send the auth frame in existing WS tests**

In `apps/daemon/tests/api/test_ws.py`, immediately after each `websocket_connect("/ws") as ws:` (and the two-socket variant `as a, ... as b:`), send the auth frame before the first `receive_json`:

```python
        ws.send_json({"type": "auth", "token": "test-token"})
```
(for the multi-subscriber test: `a.send_json({"type": "auth", "token": "test-token"})` and the same for `b`).

In `apps/daemon/tests/api/test_ws_tasks.py`, after each `websocket_connect("/ws") as ws:`:

```python
        ws.send_json({"type": "auth", "token": "test-token"})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project apps/daemon pytest apps/daemon/tests/api/test_ws.py apps/daemon/tests/api/test_ws_tasks.py -q`
Expected: PASS — reject cases disconnect; authenticated cases receive `connection.established` and stream as before.

- [ ] **Step 5: Commit**

```bash
git add apps/daemon/src/omnimac_daemon/api/ws.py apps/daemon/tests/api/test_ws.py \
        apps/daemon/tests/api/test_ws_tasks.py
git commit -m "feat(api): WebSocket first-message auth handshake" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Desktop client attaches the token

**Files:**
- Create: `apps/desktop/src/lib/auth.ts`
- Modify: `apps/desktop/src/lib/api.ts`, `apps/desktop/src/lib/ws.ts`
- Test: `apps/desktop/src/lib/auth.test.ts`, `apps/desktop/src/lib/api.test.ts`, `apps/desktop/src/lib/ws.test.ts`

**Interfaces:**
- Produces: `getSessionToken(): Promise<string | null>`, `__resetTokenCache()` (test helper). `request()` sends `Authorization: Bearer`. `WsClient` sends `{type:"auth",token}` on open.

- [ ] **Step 1: Write the failing tests**

```ts
// apps/desktop/src/lib/auth.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { __resetTokenCache, getSessionToken } from "./auth";

afterEach(() => {
  __resetTokenCache();
  delete (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
});

describe("getSessionToken", () => {
  it("uses the Tauri command when running under Tauri", async () => {
    const invoke = vi.fn().mockResolvedValue("tauri-token");
    (window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = { invoke };
    expect(await getSessionToken()).toBe("tauri-token");
    expect(invoke).toHaveBeenCalledWith("session_token");
  });

  it("falls back to VITE_OmniMac_TOKEN in the dev browser", async () => {
    vi.stubEnv("VITE_OmniMac_TOKEN", "dev-token");
    expect(await getSessionToken()).toBe("dev-token");
    vi.unstubAllEnvs();
  });
});
```

```ts
// apps/desktop/src/lib/api.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";
import { __resetTokenCache } from "./auth";

afterEach(() => {
  __resetTokenCache();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("api request auth", () => {
  it("attaches the bearer header when a token is available", async () => {
    vi.stubEnv("VITE_OmniMac_TOKEN", "dev-token");
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await api.listTasks();
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer dev-token");
  });
});
```

```ts
// apps/desktop/src/lib/ws.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { __resetTokenCache } from "./auth";
import { WsClient } from "./ws";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {}
}

afterEach(() => {
  __resetTokenCache();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  FakeWebSocket.instances = [];
});

describe("WsClient auth", () => {
  it("sends the auth frame on open", async () => {
    vi.stubEnv("VITE_OmniMac_TOKEN", "dev-token");
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    const client = new WsClient({ onEvent: () => {}, onStatus: () => {} });
    client.connect();
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1));
    const ws = FakeWebSocket.instances[0];
    ws.onopen?.();
    expect(JSON.parse(ws.sent[0])).toEqual({ type: "auth", token: "dev-token" });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm -C apps/desktop test -- --run src/lib/auth.test.ts src/lib/api.test.ts src/lib/ws.test.ts`
Expected: FAIL — `./auth` does not exist; header/frame not attached.

- [ ] **Step 3a: auth.ts**

```ts
// apps/desktop/src/lib/auth.ts
/**
 * Session token provider. Under Tauri the token comes from the daemon-written
 * file via the `session_token` command; in the dev browser it comes from
 * VITE_OmniMac_TOKEN. Held in memory only — never persisted client-side.
 */
interface TauriInternals {
  invoke: (cmd: string, args?: unknown) => Promise<unknown>;
}

function tauriInternals(): TauriInternals | null {
  const w = window as unknown as { __TAURI_INTERNALS__?: TauriInternals };
  return w.__TAURI_INTERNALS__ ?? null;
}

let cached: string | null | undefined;

export async function getSessionToken(): Promise<string | null> {
  if (cached !== undefined) return cached;
  const internals = tauriInternals();
  if (internals) {
    try {
      cached = ((await internals.invoke("session_token")) as string | null) ?? null;
    } catch {
      cached = null;
    }
  } else {
    cached = (import.meta.env.VITE_OmniMac_TOKEN as string | undefined) ?? null;
  }
  return cached;
}

/** Test-only: clear the in-memory cache. */
export function __resetTokenCache(): void {
  cached = undefined;
}
```

- [ ] **Step 3b: api.ts — attach header**

Replace the `request` function body in `apps/desktop/src/lib/api.ts` and add the import:

```ts
import { getSessionToken } from "./auth";
```

```ts
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getSessionToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string>) ?? {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch(`${DAEMON_URL}${path}`, { ...init, headers });
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(resp.status, body || resp.statusText);
  }
  return (await resp.json()) as T;
}
```

- [ ] **Step 3c: ws.ts — send auth frame**

Add the import and rewrite `open()` in `apps/desktop/src/lib/ws.ts`:

```ts
import { getSessionToken } from "./auth";
```

```ts
  private open(): void {
    this.options.onStatus("connecting");
    void getSessionToken().then((token) => {
      const url = DAEMON_URL.replace(/^http/, "ws") + "/ws";
      const ws = new WebSocket(url);
      this.ws = ws;
      ws.onopen = () => {
        ws.send(JSON.stringify({ type: "auth", token }));
        this.retryMs = 500;
        this.options.onStatus("connected");
      };
      ws.onmessage = (msg) => {
        try {
          this.options.onEvent(JSON.parse(msg.data as string) as WsEnvelope);
        } catch {
          // Malformed frame: ignore rather than kill the stream.
        }
      };
      ws.onclose = () => {
        this.options.onStatus("disconnected");
        if (!this.closedByUser) {
          this.timer = setTimeout(() => this.open(), this.retryMs);
          this.retryMs = Math.min(this.retryMs * 2, 8000);
        }
      };
      ws.onerror = () => {
        ws.close();
      };
    });
  }
```

- [ ] **Step 4: Run tests + typecheck to verify they pass**

Run: `pnpm -C apps/desktop test -- --run && pnpm -C apps/desktop typecheck`
Expected: PASS — new auth tests green; existing desktop tests unaffected; tsc clean.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/lib/auth.ts apps/desktop/src/lib/api.ts apps/desktop/src/lib/ws.ts \
        apps/desktop/src/lib/auth.test.ts apps/desktop/src/lib/api.test.ts apps/desktop/src/lib/ws.test.ts
git commit -m "feat(desktop): attach session token to HTTP + WS (Tauri command / dev env)" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Tauri command, dev token, docs, full gate

**Files:**
- Modify: `apps/desktop/src-tauri/src/lib.rs`, `Makefile`, `docs/DECISIONS.md`, `docs/THREAT_MODEL.md`, `docs/STATUS.md`, `docs/MILESTONES.md`

- [ ] **Step 1: Tauri command**

Replace `apps/desktop/src-tauri/src/lib.rs`:

```rust
// OmniMac desktop shell. The `session_token` command is the first — and only —
// custom command: it hands the daemon-issued session token to the webview so
// the thin client can authenticate. Reviewed capability (Phase 3 slice 2).

#[tauri::command]
fn session_token() -> Option<String> {
    if let Ok(t) = std::env::var("OmniMac_SESSION_TOKEN") {
        if !t.is_empty() {
            return Some(t);
        }
    }
    let path = std::env::var("OmniMac_SESSION_TOKEN_PATH")
        .unwrap_or_else(|_| "data/session.token".to_string());
    std::fs::read_to_string(path).ok().map(|s| s.trim().to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![session_token])
        .run(tauri::generate_context!())
        .expect("error while running OmniMac desktop");
}
```

- [ ] **Step 2: Verify Rust compiles**

Run: `cd apps/desktop/src-tauri && cargo check`
Expected: `Finished`. (If the environment lacks the Rust/Tauri toolchain, note it and rely on the live `make dev` smoke test instead.)

- [ ] **Step 3: Shared dev token in the Makefile**

In `Makefile`, add a variable near the top (after `DESKTOP :=`):

```make
DEV_TOKEN := omnimac-dev-token
```

and set it on both dev processes:

```make
daemon: ## Run the FastAPI daemon (http://127.0.0.1:7710)
	OmniMac_SESSION_TOKEN=$(DEV_TOKEN) uv run --project $(DAEMON) python -m omnimac_daemon.main

desktop: ## Run the desktop dev server (browser mode)
	VITE_OmniMac_TOKEN=$(DEV_TOKEN) pnpm -C $(DESKTOP) dev
```

- [ ] **Step 4: Docs**

Append to `docs/DECISIONS.md`:

```markdown
## ADR-012: Per-session bearer token for desktop↔daemon
**Date:** 2026-07-12 · **Status:** Accepted
The daemon mints a `secrets.token_urlsafe(32)` session token at startup (or reads `OmniMac_SESSION_TOKEN`), stores it on `app.state`, and writes it 0600 for the desktop to read. An HTTP middleware requires `Authorization: Bearer <token>` (constant-time `secrets.compare_digest`) on every route except `/api/health`; the WebSocket requires a first-message `{type:"auth",token}` handshake (browsers can't set WS headers). Auth is always on — no disable flag to ship off. Rejected: query-param WS token (URL logging); a runtime bypass flag (ship-off risk); OS-keychain handoff (heavier than warranted for an ephemeral per-session token). This is a deliberate, scoped exception to "no secrets in frontend state": the token is IPC auth material, held in webview memory only, never persisted client-side, and redacted from logs/audit.
```

In `docs/THREAT_MODEL.md`, update the T6 row and residual-risk bullet: mitigation is now implemented (per-session bearer token + WS handshake), not "planned".

In `docs/STATUS.md`: note slice 2 landed — the daemon now requires a session token on all endpoints except health; desktop attaches it; auth always-on. Keep the "cannot control the computer" statement. Bump the daemon test count.

In `docs/MILESTONES.md` Phase 3, add:

```markdown
- [x] **Slice 2 — Session auth token:** per-session bearer, HTTP middleware + WS handshake, desktop attaches it (Tauri command / dev env). Auth always-on.
```

- [ ] **Step 5: Full gate**

```bash
uv run --project apps/daemon pytest apps/daemon/tests -q
uv run --project apps/daemon ruff check apps/daemon && uv run --project apps/daemon ruff format --check apps/daemon
uv run --project apps/daemon mypy apps/daemon/src
pnpm -C apps/desktop test -- --run && pnpm -C apps/desktop lint && pnpm -C apps/desktop typecheck && pnpm -C apps/desktop build
```
Expected: all green.

- [ ] **Step 6: Live smoke test**

Start the daemon with a known token; confirm 401 without it, 200 with it, health open, WS handshake:

```bash
SCRATCH=<scratchpad>
OmniMac_SESSION_TOKEN=smoketoken OmniMac_DB_PATH="$SCRATCH/a.db" OmniMac_LOG_DIR="$SCRATCH/logs" \
  OmniMac_SESSION_TOKEN_PATH="$SCRATCH/session.token" \
  uv run --project apps/daemon uvicorn omnimac_daemon.app:create_app --factory --port 7712 &
curl -s -o /dev/null -w "health=%{http_code}\n" http://127.0.0.1:7712/api/health          # 200
curl -s -o /dev/null -w "noauth=%{http_code}\n" http://127.0.0.1:7712/api/tasks            # 401
curl -s -o /dev/null -w "auth=%{http_code}\n" -H "Authorization: Bearer smoketoken" http://127.0.0.1:7712/api/tasks  # 200
stat -f "%Lp" "$SCRATCH/session.token"   # 600
# kill the server
```

- [ ] **Step 7: Commit**

```bash
git add apps/desktop/src-tauri/src/lib.rs Makefile docs/DECISIONS.md docs/THREAT_MODEL.md docs/STATUS.md docs/MILESTONES.md
git commit -m "feat(desktop): session_token Tauri command; dev token; docs + threat model for slice 2" \
           -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:** §3 token primitives → T1; §5 HTTP guard + §4 lifecycle → T2; §6 WS guard → T3; §7 desktop client → T4 (+ Rust in T5); §7 Rust command + dev handoff → T5; §9 tests → each task; §11 ADR/threat-model → T5.

**Placeholder scan:** no TBD; the only fill-ins are the scratchpad path in the smoke test (Step 6) and choosing the next ADR number, both flagged. `cargo check` is guarded with a fallback if the toolchain is absent.

**Type consistency:** `mint_token()->str`, `write_token_file(path,token)->None`, `token_matches(provided,expected)->bool`, `require_bearer(request,call_next)->Response`, `getSessionToken()->Promise<string|null>`, `__resetTokenCache()->void`, WS frame `{type:"auth",token}` — consistent across daemon (T1–T3), desktop (T4), and the smoke test (T5).
