import stat
from pathlib import Path

from omnimac_daemon.security.auth import mint_token, token_matches, write_token_file


def test_mint_token_is_long_and_unique() -> None:
    a, b = mint_token(), mint_token()
    assert len(a) >= 32 and a != b


def test_write_token_file_is_0600_with_exact_contents(tmp_path: Path) -> None:
    p = tmp_path / "sub" / "session.token"
    write_token_file(p, "abc123")
    assert p.read_text() == "abc123"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_write_token_file_tightens_existing_perms(tmp_path: Path) -> None:
    p = tmp_path / "session.token"
    p.write_text("old")
    p.chmod(0o644)
    write_token_file(p, "new")
    assert p.read_text() == "new"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_token_matches() -> None:
    assert token_matches("s3cret", "s3cret")
    assert not token_matches("s3cret", "other")
    assert not token_matches(None, "s3cret")
    assert not token_matches("s3cret", None)
    assert not token_matches("", "")
