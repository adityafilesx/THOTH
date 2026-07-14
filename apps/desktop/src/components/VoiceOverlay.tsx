import { Mic, SendHorizontal, Square, Waves } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { LocalPcmRecorder } from "@/lib/pcmRecorder";

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

const MINIMUM_CAPTURE_MS = 500;
const MAXIMUM_CAPTURE_MS = 30_000;
const PARTIAL_TRANSCRIPTION_INTERVAL_MS = 750;

interface RecorderStopTarget {
  state: RecordingState;
  requestData: () => void;
  stop: () => void;
}

export function captureStopDelay(startedAt: number, now: number): number {
  return Math.max(0, MINIMUM_CAPTURE_MS - (now - startedAt));
}

export function flushAndStopRecorder(recorder: RecorderStopTarget): boolean {
  if (recorder.state !== "recording") return false;
  recorder.requestData();
  recorder.stop();
  return true;
}

export function shouldRequestPartial(
  lastRequestedAt: number | null,
  now: number,
  recordingStartedAt: number,
  interval = PARTIAL_TRANSCRIPTION_INTERVAL_MS,
): boolean {
  return now - (lastRequestedAt ?? recordingStartedAt) >= interval;
}

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

export function VoiceOverlay({
  listenForNativeEvents = true,
  hideWhenIdle = false,
}: {
  listenForNativeEvents?: boolean;
  hideWhenIdle?: boolean;
}) {
  const [state, setState] = useState<VoiceOverlayState>("idle");
  const [partial, setPartial] = useState("");
  const [finalText, setFinalText] = useState("");
  const [route, setRoute] = useState<VoiceRoute | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sessionId = useRef<string | null>(null);
  const recorder = useRef<LocalPcmRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const uploads = useRef<Promise<unknown>>(Promise.resolve());
  const autoSubmit = useRef<number | null>(null);
  const stopTimer = useRef<number | null>(null);
  const captureLimitTimer = useRef<number | null>(null);
  const recordingStartedAt = useRef<number | null>(null);
  const releaseRequested = useRef(false);
  const cancelRequested = useRef(false);
  const startInFlight = useRef(false);
  const capturedAudioBytes = useRef(0);
  const lastPartialRequestedAt = useRef<number | null>(null);
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
    recordingStartedAt.current = null;
  }, []);

  const clearStopTimer = useCallback(() => {
    if (stopTimer.current !== null) window.clearTimeout(stopTimer.current);
    if (captureLimitTimer.current !== null) window.clearTimeout(captureLimitTimer.current);
    stopTimer.current = null;
    captureLimitTimer.current = null;
  }, []);

  const stopAfterMinimumCapture = useCallback(() => {
    const activeRecorder = recorder.current;
    const startedAt = recordingStartedAt.current;
    if (!activeRecorder || startedAt === null || activeRecorder.state !== "recording") return;
    if (stopTimer.current !== null) return;
    const delay = captureStopDelay(startedAt, performance.now());
    const stop = () => {
      stopTimer.current = null;
      if (captureLimitTimer.current !== null) {
        window.clearTimeout(captureLimitTimer.current);
        captureLimitTimer.current = null;
      }
      const currentRecorder = recorder.current;
      if (currentRecorder) flushAndStopRecorder(currentRecorder);
    };
    if (delay === 0) stop();
    else stopTimer.current = window.setTimeout(stop, delay);
  }, []);

  const cancel = useCallback(async () => {
    if (autoSubmit.current !== null) window.clearTimeout(autoSubmit.current);
    clearStopTimer();
    cancelRequested.current = true;
    releaseRequested.current = false;
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
  }, [changeState, clearStopTimer, closeOverlay, stopTracks]);

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
      if (capturedAudioBytes.current === 0) {
        await api.cancelVoiceSession(id).catch(() => {});
        sessionId.current = null;
        setError("No audio was captured. Hold push-to-talk while speaking, then release.");
        changeState("failed");
        return;
      }
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
    releaseRequested.current = true;
    stopAfterMinimumCapture();
  }, [stopAfterMinimumCapture]);

  const start = useCallback(async () => {
    if (startInFlight.current || !["idle", "failed"].includes(state)) return;
    startInFlight.current = true;
    clearStopTimer();
    releaseRequested.current = false;
    cancelRequested.current = false;
    capturedAudioBytes.current = 0;
    lastPartialRequestedAt.current = null;
    uploads.current = Promise.resolve();
    setError(null);
    setPartial("");
    setFinalText("");
    setRoute(null);
    try {
      const snapshot = await api.startVoiceSession("hold");
      sessionId.current = snapshot.session_id;
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      const pcmRecorder = new LocalPcmRecorder(stream.current);
      recorder.current = pcmRecorder;
      pcmRecorder.addEventListener("dataavailable", (event) => {
        const data = (event as BlobEvent).data;
        if (!data.size || !sessionId.current) return;
        capturedAudioBytes.current += data.size;
        const id = sessionId.current;
        const now = performance.now();
        const startedAt = recordingStartedAt.current ?? now;
        const requestPartial = shouldRequestPartial(
          lastPartialRequestedAt.current,
          now,
          startedAt,
        );
        if (requestPartial) lastPartialRequestedAt.current = now;
        uploads.current = uploads.current.then(() => {
          if (sessionId.current !== id) return undefined;
          return api.appendVoiceAudio(id, data);
        });
        if (requestPartial) {
          uploads.current = uploads.current
            .then(() => {
              if (sessionId.current !== id) return undefined;
              return api.voicePartial(id);
            })
            .then((next) => {
              if (next && sessionId.current === id) setPartial(next.partial?.text ?? "");
            })
            .catch((caught: unknown) => {
              setError(caught instanceof Error ? caught.message : "Partial transcription failed.");
            });
        }
      });
      pcmRecorder.addEventListener(
        "stop",
        () => {
          if (!cancelRequested.current) void finalise();
        },
        { once: true },
      );
      pcmRecorder.start();
      recordingStartedAt.current = performance.now();
      captureLimitTimer.current = window.setTimeout(() => {
        releaseRequested.current = true;
        stopAfterMinimumCapture();
      }, MAXIMUM_CAPTURE_MS);
      changeState("listening");
      if (releaseRequested.current) stopAfterMinimumCapture();
    } catch (caught) {
      const id = sessionId.current;
      if (id) await api.cancelVoiceSession(id).catch(() => {});
      sessionId.current = null;
      stopTracks();
      setError(caught instanceof Error ? caught.message : "Microphone is unavailable.");
      changeState("failed");
    } finally {
      startInFlight.current = false;
    }
  }, [changeState, clearStopTimer, finalise, state, stopAfterMinimumCapture, stopTracks]);

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
      clearStopTimer();
      stopTracks();
    };
  }, [clearStopTimer, listenForNativeEvents, release, start, stopTracks]);

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

  return hideWhenIdle && state === "idle" ? null : (
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
