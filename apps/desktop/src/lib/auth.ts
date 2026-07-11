/**
 * Session token provider. Under Tauri the token comes from the daemon-written
 * file via the `session_token` command; in the dev browser it comes from
 * VITE_THOTH_TOKEN. Held in memory only — never persisted client-side.
 */
interface TauriInternals {
  invoke: (cmd: string, args?: unknown) => Promise<unknown>;
}

function tauriInternals(): TauriInternals | null {
  const w = window as unknown as { __TAURI_INTERNALS__?: TauriInternals };
  return w.__TAURI_INTERNALS__ ?? null;
}

let cached: string | null | undefined;

export async function getSessionToken(): Promise<string | null> {
  if (cached !== undefined) return cached;
  const internals = tauriInternals();
  if (internals) {
    try {
      cached =
        ((await internals.invoke("session_token")) as string | null) ?? null;
    } catch {
      cached = null;
    }
  } else {
    cached = (import.meta.env.VITE_THOTH_TOKEN as string | undefined) ?? null;
  }
  return cached;
}

/** Test-only: clear the in-memory cache. */
export function __resetTokenCache(): void {
  cached = undefined;
}
