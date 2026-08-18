/**
 * Session token provider. Under Tauri the token comes from the daemon-written
 * file via the `session_token` command; in the dev browser it comes from
 * VITE_OmniMac_TOKEN. Held in memory only — never persisted client-side.
 */
interface TauriInternals {
  invoke: (cmd: string, args?: unknown) => Promise<unknown>;
}

function tauriInternals(): TauriInternals | null {
  const w = window as unknown as { __TAURI_INTERNALS__?: TauriInternals };
  return w.__TAURI_INTERNALS__ ?? null;
}

let cached: string | null | undefined;
let pending: Promise<string | null> | null = null;

async function resolveSessionToken(): Promise<string | null> {
  const internals = tauriInternals();
  const explicitDevToken =
    (import.meta.env.VITE_OmniMac_TOKEN as string | undefined) ?? null;
  if (internals) {
    try {
      const nativeToken = (await internals.invoke("session_token", {})) as
        | string
        | null;
      return nativeToken || explicitDevToken;
    } catch {
      return explicitDevToken;
    }
  }
  return explicitDevToken;
}

export function getSessionToken(): Promise<string | null> {
  if (cached !== undefined) return Promise.resolve(cached);
  if (!pending) {
    pending = resolveSessionToken().then((token) => {
      cached = token;
      pending = null;
      return token;
    });
  }
  return pending;
}

/** Test-only: clear the in-memory cache. */
export function __resetTokenCache(): void {
  cached = undefined;
  pending = null;
}
