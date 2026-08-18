import { Ear, SendHorizontal } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { StateLadder } from "@/components/StateLadder";
import { OperationalSummary } from "@/components/OperationalSummary";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { native } from "@/lib/native";
import { useTasksStore } from "@/stores/tasks";

export function CommandCenter() {
  const [goal, setGoal] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [controlResponse, setControlResponse] = useState<string | null>(null);
  const pushToTalkActive = useRef(false);
  const tasks = useTasksStore((s) => s.tasks);
  const activeTaskId = useTasksStore((s) => s.activeTaskId);
  const setActiveTask = useTasksStore((s) => s.setActiveTask);
  const upsertTask = useTasksStore((s) => s.upsertTask);

  const active = activeTaskId ? tasks[activeTaskId] : null;

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const beginPushToTalk = useCallback(() => {
    if (pushToTalkActive.current) return;
    pushToTalkActive.current = true;
    void native.beginPushToTalk();
  }, []);

  const endPushToTalk = useCallback(() => {
    if (!pushToTalkActive.current) return;
    pushToTalkActive.current = false;
    void native.endPushToTalk();
  }, []);

  useEffect(() => {
    window.addEventListener("pointerup", endPushToTalk);
    window.addEventListener("pointercancel", endPushToTalk);
    return () => {
      window.removeEventListener("pointerup", endPushToTalk);
      window.removeEventListener("pointercancel", endPushToTalk);
      endPushToTalk();
    };
  }, [endPushToTalk]);

  const submit = async () => {
    const trimmed = goal.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    setError(null);
    setControlResponse(null);
    try {
      const result = await api.dispatchCommand(trimmed, "text");
      setControlResponse(result.response?.display.text ?? null);
      if (result.task) {
        upsertTask(result.task);
        setActiveTask(result.task.id);
      }
      setGoal("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reach the daemon");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col gap-4">
      {active?.presentation && (
        <OperationalSummary presentation={active.presentation} />
      )}

      {controlResponse && (
        <Card aria-label="OmniMac control response">
          <CardContent>
            <div className="eyebrow mb-1">OmniMac</div>
            <p className="text-sm text-ink" aria-live="polite">
              {controlResponse}
            </p>
          </CardContent>
        </Card>
      )}

      <div className="flex min-h-0 flex-1 gap-4">
        <Card className="w-56 shrink-0 overflow-y-auto">
          <CardContent className="p-3">
            <div className="eyebrow mb-2">task lifecycle</div>
            <StateLadder current={active?.state ?? null} />
          </CardContent>
        </Card>

        <Card className="min-w-0 flex-1 overflow-y-auto">
          <CardContent>
            {active ? (
              <div className="flex flex-col gap-3">
                <div>
                  <div className="eyebrow mb-1">goal</div>
                  <p className="text-sm text-ink">{active.goal}</p>
                </div>
                {active.result_summary && (
                  <div>
                    <div className="eyebrow mb-1">result</div>
                    <p className="text-sm text-ink">{active.result_summary}</p>
                  </div>
                )}
                {active.error && (
                  <div>
                    <div className="eyebrow mb-1 text-danger">failure</div>
                    <p className="text-xs text-danger">
                      {active.presentation?.display_response ??
                        "The task failed. No completion was claimed."}
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 py-16 text-center">
                <p className="text-sm text-muted">No task running.</p>
                <p className="text-xs text-faint">
                  Type a goal below — OmniMac plans it, classifies every step by
                  risk, and asks before anything leaves this machine.
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {error && (
        <p role="alert" className="font-mono text-xs text-danger">
          {error}
        </p>
      )}

      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <Button
          variant="outline"
          size="icon"
          aria-label="Click to talk"
          title="Click to talk"
          type="button"
          onClick={() => {
            const evt = new CustomEvent("omnimac:ptt", { detail: { state: "Pressed" } });
            window.dispatchEvent(evt);
          }}
        >
          <Ear size={14} />
        </Button>
        <Input
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="State a goal, e.g. “continue the omnimac project”"
          aria-label="Goal"
          className="h-10 font-mono"
        />
        <Button
          type="submit"
          size="lg"
          disabled={!goal.trim() || submitting}
          aria-label="Send goal"
        >
          <SendHorizontal size={14} />
          Run
        </Button>
      </form>
    </div>
  );
}
