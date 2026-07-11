from pathlib import Path

import pytest

from thoth_daemon.tools.fs_tools import FsListDir, FsReadFile, FsStat


async def test_fs_read_file_reads_real_content(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_text("hello")
    tool = FsReadFile()
    out = await tool.run(tool.input_model(path=str(p)), dry_run=False)
    assert out.content == "hello" and out.bytes == 5 and out.truncated is False


async def test_fs_read_file_binary_raises(tmp_path: Path) -> None:
    p = tmp_path / "b.bin"
    p.write_bytes(b"\xff\xfe")
    tool = FsReadFile()
    with pytest.raises(ValueError):
        await tool.run(tool.input_model(path=str(p)), dry_run=False)


async def test_fs_list_dir_lists_entries(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "f.txt").write_text("x")
    tool = FsListDir()
    out = await tool.run(tool.input_model(path=str(tmp_path)), dry_run=False)
    by_name = {e.name: e.is_dir for e in out.entries}
    assert by_name == {"sub": True, "f.txt": False}


async def test_fs_list_dir_on_file_raises(tmp_path: Path) -> None:
    p = tmp_path / "f.txt"
    p.write_text("x")
    tool = FsListDir()
    with pytest.raises(NotADirectoryError):
        await tool.run(tool.input_model(path=str(p)), dry_run=False)


async def test_fs_stat_existing_and_missing(tmp_path: Path) -> None:
    p = tmp_path / "f.txt"
    p.write_text("abc")
    tool = FsStat()
    out = await tool.run(tool.input_model(path=str(p)), dry_run=False)
    assert out.exists and out.is_file and out.size == 3
    missing = await tool.run(tool.input_model(path=str(tmp_path / "nope")), dry_run=False)
    assert missing.exists is False


def test_read_tools_declare_scope_and_redaction() -> None:
    tool = FsReadFile()
    scope = tool.requested_scope(tool.input_model(path="~/x"))
    assert scope.paths == ["~/x"]
    assert "content" in FsReadFile.redaction_fields
