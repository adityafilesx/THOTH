import { LocalPcmRecorder } from "./pcmRecorder";

export type WakeWordStatus = "connecting" | "listening" | "detected" | "error" | "closed";

export interface WakeWordClientOptions {
  onStatusChange: (status: WakeWordStatus) => void;
  onDetection: () => void;
  onError?: (error: Error) => void;
}

export class WakeWordClient {
  private ws: WebSocket | null = null;
  private recorder: LocalPcmRecorder | null = null;
  private stream: MediaStream | null = null;
  private options: WakeWordClientOptions;

  constructor(options: WakeWordClientOptions) {
    this.options = options;
  }

  async start() {
    this.options.onStatusChange("connecting");
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.recorder = new LocalPcmRecorder(this.stream);

      // We assume daemon runs on the same host for local-first
      this.ws = new WebSocket(`ws://127.0.0.1:8000/api/voice/wakeword/stream`);
      
      this.ws.onopen = () => {
        this.options.onStatusChange("listening");
        this.recorder?.start(100); // chunk size approx 100ms
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.event === "wakeword_detected") {
            this.options.onStatusChange("detected");
            this.options.onDetection();
            this.stop(); // Stop listening once detected
          }
        } catch {
          // ignore parsing errors
        }
      };

      this.ws.onerror = () => {
        this.options.onStatusChange("error");
        if (this.options.onError) {
          this.options.onError(new Error("WebSocket error in WakeWordClient"));
        }
        this.stop();
      };

      this.ws.onclose = () => {
        this.options.onStatusChange("closed");
        this.stop();
      };

      this.recorder.addEventListener("dataavailable", (event) => {
        const data = (event as BlobEvent).data;
        if (this.ws?.readyState === WebSocket.OPEN && data.size > 0) {
          this.ws.send(data);
        }
      });

    } catch (err) {
      this.options.onStatusChange("error");
      if (this.options.onError && err instanceof Error) {
        this.options.onError(err);
      }
      this.stop();
    }
  }

  stop() {
    if (this.recorder) {
      if (this.recorder.state === "recording") {
        this.recorder.stop();
      }
      this.recorder = null;
    }
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
    }
    if (this.ws) {
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close();
      }
      this.ws = null;
    }
  }
}
