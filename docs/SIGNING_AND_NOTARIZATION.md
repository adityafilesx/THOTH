# Signing and notarization validation

**Date:** 2026-07-14  
**Outcome:** blocked; development artifacts only

`security find-identity -v -p codesigning` reported zero valid identities.
No Developer ID credential, notarization profile, or staple ticket is
available. Credentials were neither requested nor exposed.

## Artifacts examined

| Artifact | Identity/result |
|---|---|
| AX helper | `me.adityalabs.thoth.axhelper`; valid ad-hoc hardened-runtime signature; no TeamIdentifier |
| Desktop app | plist `dev.thoth.desktop` version `0.1.0`; linker/ad-hoc signature |
| DMG | `THOTH_0.1.0_aarch64.dmg`, SHA-256 `cfdb93eda780377ea269068d1e4e82f48463f0ed73a163baa12ca44464dc4b1b` |

The desktop `.app` failed `codesign --verify --deep --strict`, Gatekeeper
rejected it, and `xcrun stapler validate` reported no ticket. The executable
SHA-256 was `8dfa629ed7076c75f74836b3a14957bbf8dee61ce5c19e3fa60a7ef6df90e905`.
No notarization submission was attempted because no identity exists.

Production release requires a stable production bundle identifier/version,
Developer ID signatures for the app, helper, and nested binaries, hardened
runtime/least entitlements, notarization, stapling, and clean Gatekeeper
assessment. Ad-hoc artifacts are not release evidence.

