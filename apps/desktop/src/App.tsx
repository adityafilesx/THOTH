import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ExecutionHUD } from "@/components/ExecutionHUD";
import { Layout } from "@/components/Layout";
import { VoiceOverlay } from "@/components/VoiceOverlay";
import { api } from "@/lib/api";
import { buildPresenceState } from "@/lib/presence";
import { WsClient } from "@/lib/ws";
import { useConnectionStore } from "@/stores/connection";
import { useTasksStore } from "@/stores/tasks";
import { useUiStore } from "@/stores/ui";
import { Accessibility } from "@/views/Accessibility";
import { ApprovalDrawer } from "@/views/ApprovalDrawer";
import { CommandCenter } from "@/views/CommandCenter";
import { Permissions } from "@/views/Permissions";
import { PlanView } from "@/views/PlanView";
import { Settings } from "@/views/Settings";
import { Skills } from "@/views/Skills";
import { Timeline } from "@/views/Timeline";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

function DaemonBridge() {
  const setStatus = useConnectionStore((s) => s.setStatus);
  const setDaemonVersion = useConnectionStore((s) => s.setDaemonVersion);
  const applyEvent = useTasksStore((s) => s.applyEvent);
  const setTasks = useTasksStore((s) => s.setTasks);
  const setPendingApprovals = useTasksStore((s) => s.setPendingApprovals);
  const wsRef = useRef<WsClient | null>(null);

  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15000 });

  useEffect(() => {
    if (health.data?.version) setDaemonVersion(health.data.version);
  }, [health.data?.version, setDaemonVersion]);

  useEffect(() => {
    const refreshSnapshot = () => {
      void api.listTasks().then(setTasks).catch(() => {});
      void api.pendingApprovals().then(setPendingApprovals).catch(() => {});
    };
    const ws = new WsClient({
      onEvent: applyEvent,
      onStatus: setStatus,
      onConnected: refreshSnapshot,
    });
    ws.connect();
    wsRef.current = ws;
    return () => ws.close();
  }, [applyEvent, setStatus, setTasks, setPendingApprovals]);

  return null;
}

function PresenceBridge() {
  const tasks = useTasksStore((state) => state.tasks);
  const activeTaskId = useTasksStore((state) => state.activeTaskId);
  const approvals = useTasksStore((state) => state.pendingApprovals);
  const runtime = useQuery({
    queryKey: ["runtime"],
    queryFn: api.runtime,
    refetchInterval: 5_000,
  });
  const accessibility = useQuery({
    queryKey: ["accessibility"],
    queryFn: api.accessibility,
    refetchInterval: 15_000,
  });
  const active = activeTaskId ? tasks[activeTaskId] : null;

  useEffect(() => {
    if (!runtime.data) return;
    const presence = buildPresenceState({
      taskState: active?.state ?? null,
      hasPendingApproval: approvals.length > 0,
      microphoneEnabled: true,
      voiceState: "idle",
      plannerState: runtime.data.components.planner.state,
      sttState: runtime.data.components.speech_recognition.state,
      ttsState: runtime.data.components.text_to_speech.state,
      accessibilityState: accessibility.data?.permission.status ?? "unavailable",
      privacyMode: "ephemeral",
    });
    void import("@tauri-apps/api/core")
      .then(({ invoke }) =>
        invoke("update_presence", {
          presence: {
            status: presence.status,
            current_task: presence.currentTask,
            pending_approval: presence.pendingApproval,
            microphone_enabled: presence.microphoneEnabled,
            planner_status: presence.plannerStatus,
            stt_status: presence.sttStatus,
            tts_status: presence.ttsStatus,
            accessibility_status: presence.accessibilityStatus,
            privacy_mode: presence.privacyMode,
          },
        }),
      )
      .catch(() => {});
  }, [accessibility.data?.permission.status, active?.state, approvals.length, runtime.data]);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    void import("@tauri-apps/api/event")
      .then(async ({ listen }) => {
        unlisten = await listen("thoth://stop", () => void api.globalStop("menu_bar"));
      })
      .catch(() => {});
    return () => unlisten?.();
  }, []);

  return null;
}

function ActiveExecutionHUD() {
  const tasks = useTasksStore((state) => state.tasks);
  const activeTaskId = useTasksStore((state) => state.activeTaskId);
  return <ExecutionHUD task={activeTaskId ? (tasks[activeTaskId] ?? null) : null} />;
}

function CurrentView() {
  const view = useUiStore((s) => s.view);
  switch (view) {
    case "command":
      return <CommandCenter />;
    case "plan":
      return <PlanView />;
    case "timeline":
      return <Timeline />;
    case "accessibility":
      return <Accessibility />;
    case "permissions":
      return <Permissions />;
    case "skills":
      return <Skills />;
    case "settings":
      return <Settings />;
  }
}

export default function App() {
  const [windowLabel, setWindowLabel] = useState<string | null>(null);

  useEffect(() => {
    if (!(window as unknown as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__) {
      setWindowLabel("browser");
      return;
    }
    void import("@tauri-apps/api/window")
      .then(({ getCurrentWindow }) => setWindowLabel(getCurrentWindow().label))
      .catch(() => setWindowLabel("browser"));
  }, []);

  if (windowLabel === null) return null;
  if (windowLabel === "voice-overlay") {
    return (
      <div className="p-3">
        <VoiceOverlay />
      </div>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <DaemonBridge />
      <PresenceBridge />
      <Layout>
        <CurrentView />
      </Layout>
      <ApprovalDrawer />
      <ActiveExecutionHUD />
      {windowLabel === "browser" && (
        <div className="fixed bottom-4 right-4 z-50 w-[420px]">
          <VoiceOverlay hideWhenIdle />
        </div>
      )}
    </QueryClientProvider>
  );
}
