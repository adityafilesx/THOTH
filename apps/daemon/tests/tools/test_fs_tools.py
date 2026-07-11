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


async def test_fs_write_creates_file(tmp_path: Path) -> None:
    from thoth_daemon.tools.fs_tools import FsWriteFile

    p = tmp_path / "w.txt"
    tool = FsWriteFile()
    out = await tool.run(tool.input_model(path=str(p), content="data"), dry_run=False)
    assert out.written is True and out.bytes == 4
    assert p.read_text() == "data"


async def test_fs_write_dry_run_writes_nothing(tmp_path: Path) -> None:
    from thoth_daemon.tools.fs_tools import FsWriteFile

    p = tmp_path / "w.txt"
    tool = FsWriteFile()
    out = await tool.run(tool.input_model(path=str(p), content="data"), dry_run=True)
    assert out.written is False and out.bytes == 4
    assert not p.exists()


async def test_fs_write_overwrites(tmp_path: Path) -> None:
    from thoth_daemon.tools.fs_tools import FsWriteFile

    p = tmp_path / "w.txt"
    p.write_text("old")
    tool = FsWriteFile()
    await tool.run(tool.input_model(path=str(p), content="new"), dry_run=False)
    assert p.read_text() == "new"


async def test_fs_write_missing_parent_fails(tmp_path: Path) -> None:
    from thoth_daemon.tools.fs_tools import FsWriteFile

    tool = FsWriteFile()
    with pytest.raises(FileNotFoundError):
        await tool.run(
            tool.input_model(path=str(tmp_path / "no" / "w.txt"), content="x"), dry_run=False
        )


def test_fs_write_declares_dry_run_and_scope() -> None:
    from thoth_daemon.tools.fs_tools import FsWriteFile

    tool = FsWriteFile()
    assert tool.supports_dry_run is True
    assert tool.requested_scope(tool.input_model(path="~/w", content="c")).paths == ["~/w"]
