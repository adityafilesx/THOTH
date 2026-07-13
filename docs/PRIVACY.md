# THOTH Privacy

## Local-first commitments

- All task processing, planning state, approvals, and audit data live on the user's machine (SQLite + JSONL under user-owned paths).
- The daemon binds to `127.0.0.1` only. No telemetry, no analytics, no cloud sync.
- Voice is push-to-talk only; no always-on recording, no wake word. Capture is client-side — the daemon never touches the microphone. Transcription runs locally (faster-whisper adapter; mock until a model is installed). Audio bytes are never logged; the whisper adapter writes them to a private temp file deleted immediately after transcription.
- Cloud model calls (the planning-only Anthropic Messages call — ADR-019; NOT a tool-executing agent loop) send only the normalized user goal and the tool catalog (names, risks, descriptions). Tool results, file contents, and Keychain material are never sent. The API key lives in the environment only — never in SQLite, logs, prompts, audit payloads, or frontend state. Planner-evaluation and capstone reports are redacted by construction (tool names + risk levels only; step inputs excluded).
- Phase 5 defaults remain local: routine persona responses are deterministic; optional summaries/plans use the configured loopback provider. Cloud inference is disabled unless explicitly enabled and is never a fallback.
- Foreground awareness is snapshot-on-demand. THOTH does not continuously capture screens or Accessibility trees. Window titles and selected paths redact before bounded in-memory retention.

## Data inventory

| Data | Store | Retention |
|---|---|---|
| Tasks, plans, approvals, audit events | SQLite (`THOTH_DB_PATH`) | User-configurable retention (Settings → Retention); default keep |
| Structured diagnostic logs | JSONL (`THOTH_LOG_DIR`), redacted at write | Rotated daily; user-configurable purge |
| Credentials, API keys | **macOS Keychain only** | Managed by Keychain |
| Voice audio | In-memory during push-to-talk | Discarded post-transcription |
| Foreground snapshots | In-memory only | 120 seconds by default |
| Operational dialogue references/constraints | In-memory only, task-isolated | 5 minutes; gone on restart |
| Frontend state | In-memory only | Gone on quit; never contains secrets |

## Redaction guarantee

`security/redaction.py` masks values for keys matching `password, secret, token, api_key, authorization, credential, cookie` (case-insensitive, nested) plus per-tool `redaction_fields`, at every boundary: audit-store writes, JSONL log writes, and WebSocket serialization. Tests assert redaction on each path.

## User controls

- Trusted workspaces and approved applications/directories/domains are explicit and revocable through the permissions surface.
- Planner/inference provider selection is explicit configuration; there is no silent cloud fallback.
- Operational dialogue expires automatically and is not long-term memory.

## What THOTH never does

- Store secrets in SQLite, logs, prompts, or frontend state.
- Send audio off-device.
- Keep background recordings.
- Continuously capture or retain screenshots or full Accessibility trees.
- Act on external content's instructions (see THREAT_MODEL — prompt-injection boundary).
