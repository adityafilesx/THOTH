import { Mic, SendHorizontal, Square, Waves } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

export type VoiceOverlayState =
  | "idle"
  | "listening"
  | "transcribing"
  | "ready"
  | "submitting"
  | "failed";

export type VoiceRoute = "reflex" | "skill" | "local_planner";

const ROUTE_LABELS: Record<VoiceRoute, string> = {
  reflex: "Reflex",
  skill: "Skill",
  local_planner: "Local planner",
};

function stateLabel(state: VoiceOverlayState): string {
  return state.replace(/^./, (first) => first.toUpperCase());
}

export interface VoiceOverlayViewProps {
  state: VoiceOverlayState;
  partial: string;
  finalText: string;
  route: VoiceRoute | null;
  error: string | null;
  onEdit: (text: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
  onFinish?: () => void;
}

export function VoiceOverlayView({
  state,
  partial,
  finalText,
  route,
  error,
  onEdit,
  onCancel,
  onSubmit,
  onFinish,
}: VoiceOverlayViewProps) {
  const microphoneActive = state === "listening";
  return (
    <section className="rounded-2xl border border-line bg-panel/95 p-4 shadow-2xl backdrop-blur">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            data-testid="microphone-indicator"
            data-active={String(microphoneActive)}
            className={`grid h-8 w-8 place-items-center rounded-full ${
              microphoneActive ? "animate-pulse bg-danger/20 text-danger" : "bg-surface text-muted"
            }`}
          >
            {microphoneActive ? <Mic size={15} /> : <Waves size={15} />}
          </span>
          <div>
            <p className="text-sm font-medium text-ink">{stateLabel(state)}</p>
            <p className="text-[11px] text-faint">Processed locally</p>
          </div>
        </div>
        {route && (
          <span className="rounded-full border border-line px-2 py-1 text-[10px] uppercase tracking-wide text-muted">
            {ROUTE_LABELS[route]}
          </span>
        )}
      </div>

      {partial && !finalText && (
        <p className="mt-4 min-h-10 text-sm text-muted" aria-live="polite">
          {partial}
        </p>
      )}
      {finalText && (
        <Input
          className="mt-4"
          aria-label="Final transcript"
          value={finalText}
          onChange={(event) => onEdit(event.target.value)}
        />
      )}
      {error && (
        <p role="alert" className="mt-3 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-4 flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel} aria-label="Cancel voice command">
          <Square size={12} /> Cancel
        </Button>
        {state === "listening" && onFinish && (
          <Button onClick={onFinish} aria-label="Finish recording">
            <Waves size={12} /> Finish
          </Button>
        )}
        {state === "ready" && (
          <Button onClick={onSubmit} aria-label="Submit voice command">
            <SendHorizontal size={12} /> Submit
          </Button>
        )}
      </div>
    </section>
  );
}

interface PTTEvent {
  state: "Pressed" | "Released";
}

export function VoiceOverlay({ listenForNativeEvents = true }: { listenForNativeEvents?: boolean }) {
  const [state, setState] = useState<VoiceOverlayState>("idle");
  const [partial, setPartial] = useState("");
  const [finalText, setFinalText] = useState("");
  const [route, setRoute] = useState<VoiceRoute | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sessionId = useRef<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const uploads = useRef<Promise<unknown>>(Promise.resolve());
  const autoSubmit = useRef<number | null>(null);
  const lastEscape = useRef(0);

  const syncNativeState = useCallback((next: VoiceOverlayState) => {
    void import("@tauri-apps/api/core")
      .then(({ invoke }) => invoke("update_voice_state", { state: next }))
      .catch(() => {});
  }, []);

  const changeState = useCallback(
    (next: VoiceOverlayState) => {
      setState(next);
      syncNativeState(next);
    },
    [syncNativeState],
  );

  const closeOverlay = useCallback(() => {
    void import("@tauri-apps/api/core")
      .then(({ invoke }) => invoke("set_voice_overlay_visible", { visible: false }))
      .catch(() => {});
  }, []);

  const stopTracks = useCallback(() => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    recorder.current = null;
  }, []);

  const cancel = useCallback(async () => {
    if (autoSubmit.current !== null) window.clearTimeout(autoSubmit.current);
    if (recorder.current?.state === "recording") recorder.current.stop();
    stopTracks();
    const id = sessionId.current;
    sessionId.current = null;
    if (id) await api.cancelVoiceSession(id).catch(() => {});
    await api.interruptSpeech().catch(() => {});
    setPartial("");
    setFinalText("");
    setRoute(null);
    setError(null);
    changeState("idle");
    closeOverlay();
  }, [changeState, closeOverlay, stopTracks]);

  const submit = useCallback(async (textOverride?: string) => {
    const id = sessionId.current;
    const text = (textOverride ?? finalText).trim();
    if (!id || !text) return;
    if (autoSubmit.current !== null) window.clearTimeout(autoSubmit.current);
    changeState("submitting");
    try {
      await api.editVoiceTranscript(id, text);
      const routed = await api.routeIntent(text);
      setRoute(
        routed.tier === "planner"
          ? "local_planner"
          : routed.tier === "skill"
            ? "skill"
            : "reflex",
      );
      await api.submitVoiceSession(id);
      sessionId.current = null;
      changeState("idle");
      closeOverlay();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Voice submission failed.");
      changeState("failed");
    }
  }, [changeState, closeOverlay, finalText]);

  const finalise = useCallback(async () => {
    const id = sessionId.current;
    if (!id) return;
    changeState("transcribing");
    try {
      await uploads.current;
      const snapshot = await api.finaliseVoiceSession(id);
      const text = snapshot.editable_text ?? snapshot.final?.text ?? "";
      setPartial("");
      setFinalText(text);
      changeState("ready");
      autoSubmit.current = window.setTimeout(() => void submit(text), 3_000);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Local transcription failed.");
      changeState("failed");
    } finally {
      stopTracks();
    }
  }, [changeState, stopTracks, submit]);

  const release = useCallback(() => {
    if (recorder.current?.state === "recording") {
      recorder.current.stop();
    }
  }, []);

  const start = useCallback(async () => {
    if (!["idle", "failed"].includes(state)) return;
    setError(null);
    setPartial("");
    setFinalText("");
    setRoute(null);
    try {
      const snapshot = await api.startVoiceSession("hold");
      sessionId.current = snapshot.session_id;
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream.current);
      recorder.current = mediaRecorder;
      mediaRecorder.addEventListener("dataavailable", (event) => {
        if (!event.data.size || !sessionId.current) return;
        const id = sessionId.current;
        uploads.current = uploads.current
          .then(() => api.appendVoiceAudio(id, event.data))
          .then(() => api.voicePartial(id))
          .then((next) => setPartial(next.partial?.text ?? ""))
          .catch((caught: unknown) => {
            setError(caught instanceof Error ? caught.message : "Partial transcription failed.");
          });
      });
      mediaRecorder.addEventListener("stop", () => void finalise(), { once: true });
      mediaRecorder.start(500);
      changeState("listening");
    } catch (caught) {
      const id = sessionId.current;
      if (id) await api.cancelVoiceSession(id).catch(() => {});
      sessionId.current = null;
      stopTracks();
      setError(caught instanceof Error ? caught.message : "Microphone is unavailable.");
      changeState("failed");
    }
  }, [changeState, finalise, state, stopTracks]);

  useEffect(() => {
    if (!listenForNativeEvents) return;
    let unlistenPTT: (() => void) | undefined;
    let unlistenStop: (() => void) | undefined;
    void import("@tauri-apps/api/event")
      .then(async ({ listen }) => {
        unlistenPTT = await listen<PTTEvent>("thoth://ptt", ({ payload }) => {
          if (payload.state === "Pressed") void start();
          else release();
        });
        unlistenStop = await listen("thoth://stop", () => void api.globalStop("menu_bar"));
      })
      .catch(() => {});
    const browserPTT = (event: Event) => {
      const detail = (event as CustomEvent<PTTEvent>).detail;
      if (detail.state === "Pressed") void start();
      else release();
    };
    window.addEventListener("thoth:ptt", browserPTT);
    return () => {
      unlistenPTT?.();
      unlistenStop?.();
      window.removeEventListener("thoth:ptt", browserPTT);
      stopTracks();
    };
  }, [listenForNativeEvents, release, start, stopTracks]);

  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const now = performance.now();
      if (now - lastEscape.current <= 500) {
        void api.globalStop("escape");
      } else if (state !== "idle") {
        void cancel();
      } else {
        void api.interruptSpeech();
      }
      lastEscape.current = now;
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [cancel, state]);

  return (
    <VoiceOverlayView
      state={state}
      partial={partial}
      finalText={finalText}
      route={route}
      error={error}
      onEdit={setFinalText}
      onCancel={() => void cancel()}
      onSubmit={() => void submit()}
      onFinish={release}
    />
  );
}
