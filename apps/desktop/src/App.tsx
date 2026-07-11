import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { Layout } from "@/components/Layout";
import { api } from "@/lib/api";
import { WsClient } from "@/lib/ws";
import { useConnectionStore } from "@/stores/connection";
import { useTasksStore } from "@/stores/tasks";
import { useUiStore } from "@/stores/ui";
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
    const ws = new WsClient({ onEvent: applyEvent, onStatus: setStatus });
    ws.connect();
    wsRef.current = ws;
    // Initial state snapshot; WS keeps it current afterwards.
    api.listTasks().then(setTasks).catch(() => {});
    api.pendingApprovals().then(setPendingApprovals).catch(() => {});
    return () => ws.close();
  }, [applyEvent, setStatus, setTasks, setPendingApprovals]);

  return null;
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
    case "permissions":
      return <Permissions />;
    case "skills":
      return <Skills />;
    case "settings":
      return <Settings />;
  }
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <DaemonBridge />
      <Layout>
        <CurrentView />
      </Layout>
      <ApprovalDrawer />
    </QueryClientProvider>
  );
}
