import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { __resetTokenCache } from "@/lib/auth";

import { Permissions } from "./Permissions";
import { Settings } from "./Settings";
import { Skills } from "./Skills";

function renderWithQuery(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

let routes: Record<string, unknown>;
let calls: { url: string; method: string }[];

beforeEach(() => {
  vi.stubEnv("VITE_THOTH_TOKEN", "t");
  __resetTokenCache();
  calls = [];
  routes = {
    "/api/permissions": {
      workspaces: [
        {
          id: "w1",
          name: "default",
          root_path: "~/projects/thoth",
          trusted: true,
        },
      ],
      grants: [
        {
          id: "g1",
          workspace_id: "w1",
          kind: "domain",
          value: "docs.python.org",
        },
      ],
    },
    "/api/skills": [],
    "/api/settings": {
      version: "0.1.0",
      planner: "mock",
      approval_ttl_seconds: 120,
      max_retries_per_step: 2,
      max_retries_per_task: 5,
      trusted_workspaces: ["~/projects/thoth"],
      inference_provider: "deterministic",
      inference_model: "qwen3:4b",
      network_isolation: false,
    },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const u = new URL(url, "http://x");
      calls.push({ url: u.pathname, method: init?.method ?? "GET" });
      if (init?.method === "DELETE") return jsonResponse({ revoked: "g1" });
      if (init?.method === "PATCH")
        return jsonResponse({
          id: "s1",
          name: "demo",
          description: "d",
          workflow: [],
          inputs: [],
          enabled: false,
        });
      return jsonResponse(routes[u.pathname]);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  __resetTokenCache();
});

describe("Permissions (live)", () => {
  it("renders real workspaces and grants, no mock badge", async () => {
    renderWithQuery(<Permissions />);
    expect(await screen.findByText("docs.python.org")).toBeInTheDocument();
    expect(screen.getByText("~/projects/thoth")).toBeInTheDocument();
    expect(screen.queryByText(/mock data/i)).not.toBeInTheDocument();
  });

  it("revoke fires DELETE", async () => {
    renderWithQuery(<Permissions />);
    fireEvent.click(await screen.findByRole("button", { name: /revoke/i }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "DELETE")).toBe(true),
    );
  });
});

describe("Skills (live)", () => {
  it("shows empty state when no skills, no mock badge", async () => {
    renderWithQuery(<Skills />);
    expect(await screen.findByText(/no skills installed/i)).toBeInTheDocument();
    expect(screen.queryByText(/mock data/i)).not.toBeInTheDocument();
  });

  it("toggle fires PATCH", async () => {
    routes["/api/skills"] = [
      {
        id: "s1",
        name: "demo",
        description: "d",
        workflow: ["fs_stat"],
        inputs: [],
        enabled: true,
      },
    ];
    renderWithQuery(<Skills />);
    fireEvent.click(
      await screen.findByRole("switch", { name: /enable demo/i }),
    );
    await waitFor(() =>
      expect(calls.some((c) => c.method === "PATCH")).toBe(true),
    );
  });
});

describe("Settings (live)", () => {
  it("renders real config, no mock badge", async () => {
    renderWithQuery(<Settings />);
    expect(await screen.findByDisplayValue("mock")).toBeInTheDocument();
    expect(screen.getByText(/Daemon v0\.1\.0/)).toBeInTheDocument();
    expect(screen.queryByText(/mock data/i)).not.toBeInTheDocument();
  });
});
