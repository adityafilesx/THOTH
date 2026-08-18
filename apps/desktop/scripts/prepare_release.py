#!/usr/bin/env python3
"""Build and stage OmniMac's local-only macOS runtime assets for Tauri."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DAEMON = ROOT / "apps" / "daemon"
DESKTOP = ROOT / "apps" / "desktop"
TAURI = DESKTOP / "src-tauri"
HELPER = ROOT / "apps" / "ax-helper"
WHISPER = ROOT / "data" / "runtime" / "whisper.cpp-v1.8.6" / "build" / "bin" / "whisper-cli"
MODEL = ROOT / "data" / "models" / "whisper" / "ggml-base.en.bin"


def run(*args: str, cwd: Path = ROOT) -> None:
    subprocess.run(args, cwd=cwd, check=True)  # noqa: S603


def require(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is required for a release bundle: {path}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset(path: Path, relative_path: str) -> dict[str, str | int]:
    return {
        "relative_path": relative_path,
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }


def main() -> None:
    require(WHISPER, "integrity-pinned whisper.cpp executable")
    require(MODEL, "base.en Whisper model")

    build_root = TAURI / "release-build"
    pyinstaller_dist = build_root / "pyinstaller-dist"
    pyinstaller_work = build_root / "pyinstaller-work"
    pyinstaller_spec = build_root / "pyinstaller-spec"
    shutil.rmtree(build_root, ignore_errors=True)
    pyinstaller_dist.mkdir(parents=True)
    pyinstaller_work.mkdir(parents=True)
    pyinstaller_spec.mkdir(parents=True)

    run(
        "uv",
        "run",
        "--project",
        str(DAEMON),
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--name",
        "omnimac-daemon",
        "--paths",
        str(DAEMON / "src"),
        "--hidden-import",
        "aiosqlite",
        "--distpath",
        str(pyinstaller_dist),
        "--workpath",
        str(pyinstaller_work),
        "--specpath",
        str(pyinstaller_spec),
        str(DAEMON / "src" / "omnimac_daemon" / "main.py"),
    )
    run(str(HELPER / "scripts" / "package.sh"))

    resources = TAURI / "resources"
    shutil.rmtree(resources, ignore_errors=True)
    (resources / "runtime").mkdir(parents=True)
    (resources / "models").mkdir(parents=True)

    daemon_target = resources / "runtime" / "omnimac-daemon"
    helper_app = resources / "OmniMac Accessibility Helper.app"
    helper_executable = helper_app / "Contents" / "MacOS" / "OmniMacAXHelper"
    whisper_target = resources / "runtime" / "whisper-cli"
    model_target = resources / "models" / "ggml-base.en.bin"
    shutil.copy2(pyinstaller_dist / "omnimac-daemon", daemon_target)
    shutil.copytree(HELPER / "dist" / "OmniMac Accessibility Helper.app", helper_app)
    shutil.copy2(WHISPER, whisper_target)
    shutil.copy2(MODEL, model_target)
    for executable in (daemon_target, helper_executable, whisper_target):
        executable.chmod(executable.stat().st_mode | 0o755)

    manifest = {
        "schema_version": 1,
        "daemon": asset(daemon_target, "runtime/omnimac-daemon"),
        "helper": asset(
            helper_executable,
            "OmniMac Accessibility Helper.app/Contents/MacOS/OmniMacAXHelper",
        ),
        "whisper_executable": asset(whisper_target, "runtime/whisper-cli"),
        "whisper_model": asset(model_target, "models/ggml-base.en.bin"),
    }
    manifest_path = resources / "runtime-manifest.json"
    temporary_manifest = manifest_path.with_suffix(".tmp")
    temporary_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_manifest, manifest_path)
    print(f"Prepared OmniMac runtime: {manifest_path}")


if __name__ == "__main__":
    main()
