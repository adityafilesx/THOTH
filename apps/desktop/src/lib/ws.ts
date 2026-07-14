/**
 * Reconnecting WebSocket client for the daemon event stream.
 * Dispatches every envelope to the handler; reconnects with capped backoff.
 */
import type { WsEnvelope } from "@thoth/shared-schemas";

import { DAEMON_URL } from "./api";
import { getSessionToken } from "./auth";

export type WsStatus = "connecting" | "connected" | "disconnected";

export interface WsClientOptions {
  onEvent: (envelope: WsEnvelope) => void;
  onStatus: (status: WsStatus) => void;
  onConnected?: () => void;
}

export class WsClient {
  private ws: WebSocket | null = null;
  private closedByUser = false;
  private retryMs = 500;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(private options: WsClientOptions) {}

  connect(): void {
    this.closedByUser = false;
    this.open();
  }

  private open(): void {
    this.options.onStatus("connecting");
    void getSessionToken().then((token) => {
      const url = DAEMON_URL.replace(/^http/, "ws") + "/ws";
      const ws = new WebSocket(url);
      this.ws = ws;
      ws.onopen = () => {
        ws.send(JSON.stringify({ type: "auth", token }));
      };
      ws.onmessage = (msg) => {
        try {
          const envelope = JSON.parse(msg.data as string) as WsEnvelope;
          if (envelope.type === "connection.established") {
            this.retryMs = 500;
            this.options.onStatus("connected");
            this.options.onConnected?.();
          }
          this.options.onEvent(envelope);
        } catch {
          // Malformed frame: ignore rather than kill the stream.
        }
      };
      ws.onclose = () => {
        if (this.closedByUser) return;
        this.options.onStatus("disconnected");
        this.timer = setTimeout(() => this.open(), this.retryMs);
        this.retryMs = Math.min(this.retryMs * 2, 8000);
      };
      ws.onerror = () => {
        ws.close();
      };
    });
  }

  close(): void {
    this.closedByUser = true;
    if (this.timer) clearTimeout(this.timer);
    this.ws?.close();
  }
}
