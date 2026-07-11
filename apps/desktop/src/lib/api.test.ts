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
    vi.stubEnv("VITE_THOTH_TOKEN", "dev-token");
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.listTasks();
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)["Authorization"]).toBe(
      "Bearer dev-token",
    );
  });
});
