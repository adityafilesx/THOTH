# THOTH Privacy

## Local-first commitments

- All task processing, planning state, approvals, and audit data live on the user's machine (SQLite + JSONL under user-owned paths).
- The daemon binds to `127.0.0.1` only. No telemetry, no analytics, no cloud sync.
- Voice is push-to-talk only; no always-on recording, no wake word. Transcription runs locally (whisper.cpp / faster-whisper adapters, Phase 3). Audio buffers are discarded after transcription; they are never persisted.
- Cloud model calls (Phase 3 planner via claude-agent-sdk) send only: the normalized user goal, typed plan/tool context, and redacted tool results. Never raw credential material, Keychain content, or unredacted file dumps. Local processing is preferred where practical.

## Data inventory

| Data | Store | Retention |
|---|---|---|
| Tasks, plans, approvals, audit events | SQLite (`THOTH_DB_PATH`) | User-configurable retention (Settings → Retention); default keep |
| Structured diagnostic logs | JSONL (`THOTH_LOG_DIR`), redacted at write | Rotated daily; user-configurable purge |
| Credentials, API keys | **macOS Keychain only** | Managed by Keychain |
| Voice audio | In-memory during push-to-talk | Discarded post-transcription |
| Frontend state | In-memory only | Gone on quit; never contains secrets |

## Redaction guarantee

`security/redaction.py` masks values for keys matching `password, secret, token, api_key, authorization, credential, cookie` (case-insensitive, nested) plus per-tool `redaction_fields`, at every boundary: audit-store writes, JSONL log writes, and WebSocket serialization. Tests assert redaction on each path.

## User controls (Settings view)

- Retention windows for tasks, audit events, and logs.
- Trusted-workspace list (expands R1 autonomy — explicit opt-in, revocable).
- Approved applications / directories / browser domains with one-click revocation (Permissions view).
- Model configuration, including a local/mock planner mode.

## What THOTH never does

- Store secrets in SQLite, logs, prompts, or frontend state.
- Send audio off-device.
- Keep background recordings.
- Act on external content's instructions (see THREAT_MODEL — prompt-injection boundary).
