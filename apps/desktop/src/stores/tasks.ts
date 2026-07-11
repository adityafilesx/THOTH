/**
 * Task/approval/audit state fed by the WS event stream.
 * `applyEvent` is the single reducer for every daemon event type — keep it
 * exhaustive over WsEventType (compile-time checked in the default arm).
 */
import type {
  ApprovalRequest,
  AuditEvent,
  Task,
  WsEnvelope,
} from "@thoth/shared-schemas";
import { create } from "zustand";

interface TasksState {
  tasks: Record<string, Task>;
  activeTaskId: string | null;
  pendingApprovals: ApprovalRequest[];
  auditByTask: Record<string, AuditEvent[]>;
  setTasks: (tasks: Task[]) => void;
  upsertTask: (task: Task) => void;
  setActiveTask: (id: string | null) => void;
  setPendingApprovals: (approvals: ApprovalRequest[]) => void;
  setAudit: (taskId: string, events: AuditEvent[]) => void;
  applyEvent: (envelope: WsEnvelope) => void;
}

export const useTasksStore = create<TasksState>((set) => ({
  tasks: {},
  activeTaskId: null,
  pendingApprovals: [],
  auditByTask: {},

  setTasks: (tasks) =>
    set({ tasks: Object.fromEntries(tasks.map((t) => [t.id, t])) }),
  upsertTask: (task) =>
    set((s) => ({ tasks: { ...s.tasks, [task.id]: task } })),
  setActiveTask: (activeTaskId) => set({ activeTaskId }),
  setPendingApprovals: (pendingApprovals) => set({ pendingApprovals }),
  setAudit: (taskId, events) =>
    set((s) => ({ auditByTask: { ...s.auditByTask, [taskId]: events } })),

  applyEvent: (envelope) =>
    set((s) => {
      switch (envelope.type) {
        case "task.created":
        case "task.state_changed":
        case "task.step_started":
        case "task.step_finished": {
          const task = envelope.payload.task as Task | undefined;
          if (!task) return s;
          return {
            ...s,
            tasks: { ...s.tasks, [task.id]: task },
            activeTaskId: s.activeTaskId ?? task.id,
          };
        }
        case "approval.requested": {
          const approval = envelope.payload.approval as ApprovalRequest | undefined;
          if (!approval) return s;
          const rest = s.pendingApprovals.filter((a) => a.id !== approval.id);
          return { ...s, pendingApprovals: [...rest, approval] };
        }
        case "approval.decided": {
          const approval = envelope.payload.approval as ApprovalRequest | undefined;
          if (!approval) return s;
          return {
            ...s,
            pendingApprovals: s.pendingApprovals.filter((a) => a.id !== approval.id),
          };
        }
        case "audit.appended": {
          const event = envelope.payload.event as AuditEvent | undefined;
          if (!event) return s;
          const existing = s.auditByTask[event.task_id] ?? [];
          if (existing.some((e) => e.event_id === event.event_id)) return s;
          return {
            ...s,
            auditByTask: {
              ...s.auditByTask,
              [event.task_id]: [...existing, event].sort((a, b) => a.seq - b.seq),
            },
          };
        }
        case "connection.established":
          return s;
        default:
          return s;
      }
    }),
}));
