import { afterEach, describe, expect, it, vi } from "vitest";

import { __resetTokenCache, getSessionToken } from "./auth";

afterEach(() => {
  __resetTokenCache();
  delete (window as unknown as { __TAURI_INTERNALS__?: unknown })
    .__TAURI_INTERNALS__;
  vi.unstubAllEnvs();
});

describe("getSessionToken", () => {
  it("uses the Tauri command when running under Tauri", async () => {
    const invoke = vi.fn().mockResolvedValue("tauri-token");
    (
      window as unknown as { __TAURI_INTERNALS__?: unknown }
    ).__TAURI_INTERNALS__ = { invoke };
    expect(await getSessionToken()).toBe("tauri-token");
    expect(invoke).toHaveBeenCalledWith("session_token");
  });

  it("falls back to VITE_THOTH_TOKEN in the dev browser", async () => {
    vi.stubEnv("VITE_THOTH_TOKEN", "dev-token");
    expect(await getSessionToken()).toBe("dev-token");
  });
});
