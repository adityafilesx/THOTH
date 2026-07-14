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
  close() {
    this.onclose?.();
  }
}

afterEach(() => {
  __resetTokenCache();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  FakeWebSocket.instances = [];
});

describe("WsClient auth", () => {
  it("sends the auth frame on open", async () => {
    vi.stubEnv("VITE_THOTH_TOKEN", "dev-token");
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    const client = new WsClient({ onEvent: () => {}, onStatus: () => {} });
    client.connect();
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1));
    const ws = FakeWebSocket.instances[0];
    ws.onopen?.();
    expect(JSON.parse(ws.sent[0])).toEqual({
      type: "auth",
      token: "dev-token",
    });
  });

  it("does not publish a false disconnection when intentionally disposed", async () => {
    vi.stubEnv("VITE_THOTH_TOKEN", "dev-token");
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    const statuses: string[] = [];
    const client = new WsClient({
      onEvent: () => {},
      onStatus: (status) => statuses.push(status),
    });
    client.connect();
    await vi.waitFor(() => expect(FakeWebSocket.instances.length).toBe(1));
    FakeWebSocket.instances[0].onopen?.();

    client.close();

    expect(statuses).toEqual(["connecting", "connected"]);
  });
});
