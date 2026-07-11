/**
 * Reconnecting WebSocket client for the daemon event stream.
 * Dispatches every envelope to the handler; reconnects with capped backoff.
 */
import type { WsEnvelope } from "@thoth/shared-schemas";

import { DAEMON_URL } from "./api";

export type WsStatus = "connecting" | "connected" | "disconnected";

export interface WsClientOptions {
  onEvent: (envelope: WsEnvelope) => void;
  onStatus: (status: WsStatus) => void;
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
    const url = DAEMON_URL.replace(/^http/, "ws") + "/ws";
    this.ws = new WebSocket(url);
    this.ws.onopen = () => {
      this.retryMs = 500;
      this.options.onStatus("connected");
    };
    this.ws.onmessage = (msg) => {
      try {
        this.options.onEvent(JSON.parse(msg.data as string) as WsEnvelope);
      } catch {
        // Malformed frame: ignore rather than kill the stream.
      }
    };
    this.ws.onclose = () => {
      this.options.onStatus("disconnected");
      if (!this.closedByUser) {
        this.timer = setTimeout(() => this.open(), this.retryMs);
        this.retryMs = Math.min(this.retryMs * 2, 8000);
      }
    };
    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  close(): void {
    this.closedByUser = true;
    if (this.timer) clearTimeout(this.timer);
    this.ws?.close();
  }
}
