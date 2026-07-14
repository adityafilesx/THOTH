# THOTH macOS packaging

## Current artifact

`make bundle` creates an arm64 `THOTH.app` and DMG. The app is runnable without
a repository daemon, Python interpreter, `uv`, Node, or Vite. It contains:

- the Tauri/React desktop;
- a PyInstaller-frozen FastAPI daemon;
- the exact `me.adityalabs.thoth.axhelper` helper app;
- whisper.cpp v1.8.6 `whisper-cli`;
- the base.en GGML model; and
- a schema-versioned runtime manifest with authoritative relative paths, byte
  counts, and SHA-256 hashes.

The app refuses to start the managed runtime if any declared asset is missing
or changed. Rust creates a fresh 64-character bearer token in the Tauri app data
directory with mode 0600, launches both children with a minimal environment,
and requires an authenticated `/api/runtime` response before setup completes.
Normal Quit explicitly terminates and reaps both children. The daemon and helper
also monitor the desktop PID and exit if the parent is forcibly terminated.
An occupied daemon port is rejected before either child starts, so a second app
instance cannot replace the first instance's helper socket.

The merged app `Info.plist` declares microphone use narrowly: recording occurs
only during push-to-talk and transcription is local. macOS grants microphone
access per app identity, so Chrome's development permission does not grant it
to `THOTH.app`; the user must accept the native app's first-use prompt.

## Build

The builder must have the repository dependencies plus these integrity-pinned
local inputs:

```text
data/runtime/whisper.cpp-v1.8.6/build/bin/whisper-cli
data/models/whisper/ggml-base.en.bin
```

Then run:

```bash
make bundle
```

Artifacts:

```text
apps/desktop/src-tauri/target/release/bundle/macos/THOTH.app
apps/desktop/src-tauri/target/release/bundle/dmg/THOTH_0.1.0_aarch64.dmg
```

The build runs the frontend production build, freezes the daemon, packages the
Swift helper, stages the exact speech assets, writes the manifest atomically,
and lets Tauri assemble and ad-hoc sign the app and DMG. Generated binaries,
resources, and PyInstaller work products are ignored by Git.

## Verification

```bash
APP=apps/desktop/src-tauri/target/release/bundle/macos/THOTH.app
codesign --verify --deep --strict --verbose=2 "$APP"
jq . "$APP/Contents/Resources/runtime-manifest.json"
open -n "$APP"
```

On this host the final app is 217 MB and the DMG is 196 MB. Every manifest hash
matched, the DMG mounted read-only with all declared assets, strict ad-hoc code
signature verification passed, the app launched its own authenticated daemon
and helper, and normal/forced desktop termination released both children.

## Not yet release-validated

- There is no Developer ID signature, notarization ticket, staple, or
  Gatekeeper acceptance. `spctl` correctly rejects this ad-hoc artifact.
- No clean-account install, upgrade, uninstall, or first-run TCC flow has run.
- Novel planning expects loopback Ollama plus `qwen3:4b`; the 2.5 GB model is not
  copied into this DMG. Missing inference degrades locally with no cloud fallback.
- Playwright browser tools require a local Chromium payload, which this DMG does
  not install yet.
- Real microphone model selection and exact-helper TCC UI capstones remain open.

This is therefore a substantially complete local-core package and a release
candidate, not a notarized or clean-install-validated v1 release.
