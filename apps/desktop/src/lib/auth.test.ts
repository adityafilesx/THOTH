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
    expect(invoke).toHaveBeenCalledWith("session_token", {});
  });

  it("falls back to VITE_OmniMac_TOKEN in the dev browser", async () => {
    vi.stubEnv("VITE_OmniMac_TOKEN", "dev-token");
    expect(await getSessionToken()).toBe("dev-token");
  });

  it("uses the explicit dev token when native lookup fails", async () => {
    vi.stubEnv("VITE_OmniMac_TOKEN", "dev-token");
    const invoke = vi.fn().mockRejectedValue(new Error("IPC unavailable"));
    (
      window as unknown as { __TAURI_INTERNALS__?: unknown }
    ).__TAURI_INTERNALS__ = { invoke };

    expect(await getSessionToken()).toBe("dev-token");
  });

  it("uses the explicit dev token when native lookup returns no token", async () => {
    vi.stubEnv("VITE_OmniMac_TOKEN", "dev-token");
    const invoke = vi.fn().mockResolvedValue(null);
    (
      window as unknown as { __TAURI_INTERNALS__?: unknown }
    ).__TAURI_INTERNALS__ = { invoke };

    expect(await getSessionToken()).toBe("dev-token");
  });

  it("shares one native lookup across concurrent startup requests", async () => {
    let resolveToken: ((token: string) => void) | undefined;
    const token = new Promise<string>((resolve) => {
      resolveToken = resolve;
    });
    const invoke = vi.fn().mockReturnValue(token);
    (
      window as unknown as { __TAURI_INTERNALS__?: unknown }
    ).__TAURI_INTERNALS__ = { invoke };

    const first = getSessionToken();
    const second = getSessionToken();
    expect(invoke).toHaveBeenCalledTimes(1);
    resolveToken?.("tauri-token");

    await expect(Promise.all([first, second])).resolves.toEqual([
      "tauri-token",
      "tauri-token",
    ]);
  });
});
