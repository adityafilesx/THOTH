"""Low-level filesystem byte helpers for the fs tools: a size-capped UTF-8
read and an atomic write. Operate on already-scope-validated paths."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


class BinaryFileError(ValueError):
    """A file is not decodable as UTF-8 text."""


def read_text_capped(path: Path, max_bytes: int) -> tuple[str, int, bool]:
    """Return (text, byte_count, truncated). Read at most *max_bytes*; set
    truncated when the file is larger. Raise BinaryFileError for non-UTF-8
    bytes (after trimming up to 3 trailing bytes at a truncation boundary)."""
    with open(path, "rb") as f:
        raw = f.read(max_bytes + 1)
    truncated = len(raw) > max_bytes
    data = raw[:max_bytes] if truncated else raw
    try:
        return data.decode("utf-8"), len(data), truncated
    except UnicodeDecodeError:
        if truncated:
            for trim in range(1, 4):  # a multibyte char may straddle the cap
                try:
                    return data[:-trim].decode("utf-8"), len(data), True
                except UnicodeDecodeError:
                    continue
        raise BinaryFileError(f"{path} is not valid UTF-8 text") from None


def atomic_write(path: Path, data: bytes) -> None:
    """Write *data* to *path* atomically: temp file in the same directory,
    fsync, then os.replace. Parent must already exist."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".omnimac-tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
