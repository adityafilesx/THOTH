from pathlib import Path

import pytest

from thoth_daemon.tools.fs_io import BinaryFileError, atomic_write, read_text_capped


def test_read_small_file_not_truncated(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_text("hello world")
    text, n, truncated = read_text_capped(p, 1024)
    assert text == "hello world" and n == 11 and truncated is False


def test_read_over_cap_is_truncated(tmp_path: Path) -> None:
    p = tmp_path / "big.txt"
    p.write_text("x" * 100)
    text, n, truncated = read_text_capped(p, 10)
    assert len(text) == 10 and n == 10 and truncated is True


def test_read_utf8_multibyte_at_boundary(tmp_path: Path) -> None:
    p = tmp_path / "u.txt"
    p.write_bytes(("a" * 9 + "é").encode("utf-8"))  # 'é' = 2 bytes, straddles a 10-byte cap
    text, n, truncated = read_text_capped(p, 10)
    assert text == "a" * 9 and truncated is True  # partial char trimmed


def test_read_binary_raises(tmp_path: Path) -> None:
    p = tmp_path / "b.bin"
    p.write_bytes(b"\xff\xfe\x00\x01")
    with pytest.raises(BinaryFileError):
        read_text_capped(p, 1024)


def test_atomic_write_creates_exact_bytes_no_temp_left(tmp_path: Path) -> None:
    p = tmp_path / "out.txt"
    atomic_write(p, b"payload")
    assert p.read_bytes() == b"payload"
    assert [c.name for c in tmp_path.iterdir()] == ["out.txt"]  # no temp leftover


def test_atomic_write_overwrites(tmp_path: Path) -> None:
    p = tmp_path / "o.txt"
    p.write_text("old")
    atomic_write(p, b"new")
    assert p.read_bytes() == b"new"


def test_atomic_write_missing_parent_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        atomic_write(tmp_path / "nope" / "x.txt", b"data")
