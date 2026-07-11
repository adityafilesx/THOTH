import { create } from "zustand";

import type { WsStatus } from "@/lib/ws";

interface ConnectionState {
  status: WsStatus;
  daemonVersion: string | null;
  setStatus: (status: WsStatus) => void;
  setDaemonVersion: (version: string) => void;
}

export const useConnectionStore = create<ConnectionState>((set) => ({
  status: "disconnected",
  daemonVersion: null,
  setStatus: (status) => set({ status }),
  setDaemonVersion: (daemonVersion) => set({ daemonVersion }),
}));
