import { create } from "zustand";

export type View =
  | "command"
  | "plan"
  | "timeline"
  | "permissions"
  | "skills"
  | "settings";

interface UiState {
  view: View;
  approvalDrawerOpen: boolean;
  setView: (view: View) => void;
  setApprovalDrawerOpen: (open: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  view: "command",
  approvalDrawerOpen: false,
  setView: (view) => set({ view }),
  setApprovalDrawerOpen: (approvalDrawerOpen) => set({ approvalDrawerOpen }),
}));
