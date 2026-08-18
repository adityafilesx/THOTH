interface PTTEvent {
  state: "Pressed" | "Released";
}

async function invokeOrDispatch(command: string, fallback: PTTEvent): Promise<void> {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke(command);
  } catch {
    window.dispatchEvent(new CustomEvent("omnimac:ptt", { detail: fallback }));
  }
}

export const native = {
  beginPushToTalk: () => invokeOrDispatch("begin_push_to_talk", { state: "Pressed" }),
  endPushToTalk: () => invokeOrDispatch("end_push_to_talk", { state: "Released" }),
};
