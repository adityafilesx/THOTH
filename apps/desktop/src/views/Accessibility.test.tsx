import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { __resetTokenCache } from "@/lib/auth";

import { Accessibility } from "./Accessibility";

const status = {
  permission: {
    status: "not_determined",
    checked_at: "2026-07-14T18:00:00Z",
    stale_after: "2026-07-14T18:00:02Z",
    detail: "Accessibility trust is absent and no settings visit was requested",
  },
  applications: [
    {
      bundle_id: "me.adityalabs.thoth.axtest",
      display_name: "THOTH Accessibility Test App",
      version: "1.0.0",
      verified_capabilities: ["launch"],
      experimental_capabilities: ["ax_set_value"],
      forbidden_operations: ["credential_dialog"],
    },
  ],
  diagnostics: {
    current_task_id: "task-ax",
    current_step_id: "step-ax",
    current_tool: "ax.perform_action",
    bundle_id: "me.adityalabs.thoth.axtest",
    semantic_target: {
      identifier: "ax-save-button",
      role: "AXButton",
      semantic_alias: null,
    },
    resolution_method: "identifier",
    resolution_confidence: 1,
    candidate_count: 2,
    focus_policy: "restore_previous_focus",
    verification_evidence: "value_equals=failed: value did not match",
    permission_error: "Accessibility permission not_determined",
    clarification_required: true,
    updated_at: "2026-07-14T18:00:00Z",
  },
};

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Accessibility />
    </QueryClientProvider>,
  );
}

let calls: { method: string; body: string | null }[];

beforeEach(() => {
  vi.stubEnv("VITE_THOTH_TOKEN", "test-token");
  __resetTokenCache();
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) => {
      calls.push({ method: init?.method ?? "GET", body: (init?.body as string) ?? null });
      const body =
        init?.method === "POST"
          ? { opened: true, permission: status.permission }
          : status;
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  __resetTokenCache();
});

describe("Accessibility live diagnostics", () => {
  it("shows permission, capability classes, current task, target, and focus", async () => {
    renderView();
    expect(await screen.findByTestId("ax-permission-state")).toHaveTextContent(
      "not determined",
    );
    expect(screen.getByText("THOTH Accessibility Test App")).toBeInTheDocument();
    expect(screen.getByText("launch")).toBeInTheDocument();
    expect(screen.getByText("ax set value")).toBeInTheDocument();
    expect(screen.getByText("credential dialog")).toBeInTheDocument();
    expect(screen.getByTestId("ax-current-task")).toHaveTextContent("task-ax");
    expect(screen.getByTestId("ax-semantic-target")).toHaveTextContent("ax-save-button");
    expect(screen.getByTestId("ax-focus-policy")).toHaveTextContent(
      "restore previous focus",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("not_determined");
    expect(screen.getByTestId("ax-clarification")).toHaveTextContent(
      "No action was taken",
    );
  });

  it("keeps resolver and verifier evidence behind the developer switch", async () => {
    renderView();
    await screen.findByTestId("ax-permission-state");
    expect(screen.queryByTestId("ax-resolution")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ax-verification-evidence")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("switch", { name: /developer diagnostics/i }));
    expect(screen.getByTestId("ax-resolution")).toHaveTextContent("identifier · 100%");
    expect(screen.getByTestId("ax-verification-evidence")).toHaveTextContent(
      "value_equals=failed",
    );
    expect(screen.queryByText(/private document title/i)).not.toBeInTheDocument();
  });

  it("opens System Settings only from the explicit user button", async () => {
    renderView();
    fireEvent.click(
      await screen.findByRole("button", { name: /open accessibility settings/i }),
    );
    await waitFor(() => expect(calls.some((call) => call.method === "POST")).toBe(true));
    const post = calls.find((call) => call.method === "POST");
    expect(JSON.parse(post?.body ?? "{}")).toEqual({ user_requested: true });
  });
});
