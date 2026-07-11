from pathlib import Path

import pytest

from thoth_daemon.security.paths import expand_and_resolve
from thoth_daemon.security.shell_policy import (
    ShellPolicyError,
    parse_command,
    validate_executable,
)


@pytest.mark.parametrize(
    "cmd",
    ["ls; rm -rf ~", "a && b", "a | b", "echo `x`", "echo $(x)", "cat > f", "ls *.py"],
)
def test_metacharacters_rejected(cmd: str) -> None:
    with pytest.raises(ShellPolicyError):
        parse_command(cmd, "/tmp")


def test_empty_rejected() -> None:
    with pytest.raises(ShellPolicyError):
        parse_command("   ", "/tmp")


def test_plain_command_no_path_tokens() -> None:
    p = parse_command("git status", "/tmp")
    assert p.argv == ["git", "status"] and p.path_tokens == []


def test_flags_are_not_path_tokens() -> None:
    assert parse_command("git log --oneline", "/tmp").path_tokens == []


def test_absolute_path_arg_is_a_token(tmp_path: Path) -> None:
    # The resolver canonicalizes symlinks (e.g. /etc -> /private/etc on macOS);
    # assert against the resolved form, which is exactly what the enforcer checks.
    p = parse_command("cat /etc/hosts", str(tmp_path))
    assert p.path_tokens == [str(expand_and_resolve("/etc/hosts"))]


def test_relative_path_arg_resolved_against_cwd(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    p = parse_command("cat sub/x.txt", str(tmp_path))
    assert p.path_tokens == [str(tmp_path / "sub" / "x.txt")]


def test_dotdot_arg_resolves_outside(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    p = parse_command("cat ../secret", str(sub))
    assert p.path_tokens == [str(tmp_path / "secret")]


def test_validate_executable_allows_allowlisted() -> None:
    validate_executable(["git", "status"])


@pytest.mark.parametrize(
    "argv", [["sudo", "ls"], ["rm", "-rf", "x"], ["/tmp/git", "status"], ["curl", "x"]]
)
def test_validate_executable_rejects(argv: list[str]) -> None:
    with pytest.raises(ShellPolicyError):
        validate_executable(argv)
