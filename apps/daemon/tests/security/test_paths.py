from pathlib import Path

from thoth_daemon.security.paths import expand_and_resolve, is_denied_path, is_within


def test_expand_user_home() -> None:
    assert expand_and_resolve("~/projects/thoth") == (Path.home() / "projects" / "thoth").resolve()


def test_is_within_child_and_self() -> None:
    root = Path.home() / "projects" / "thoth"
    assert is_within(root / "src" / "main.py", root)
    assert is_within(root, root)


def test_is_within_rejects_parent_and_sibling() -> None:
    root = Path.home() / "projects" / "thoth"
    assert not is_within(Path.home() / "projects", root)
    assert not is_within(Path.home() / "projects" / "other", root)


def test_is_within_rejects_dotdot_escape() -> None:
    root = Path.home() / "projects" / "thoth"
    assert not is_within(root / ".." / "secret.txt", root)


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("x")
    link = root / "link.txt"
    link.symlink_to(outside / "secret.txt")
    assert not is_within(link, root)  # lives in root, resolves outside


def test_denylist_credential_dirs() -> None:
    assert is_denied_path(Path.home() / ".ssh" / "id_rsa")
    assert is_denied_path(Path.home() / ".aws" / "credentials")
    assert is_denied_path(Path.home() / ".config" / "gcloud" / "creds.db")
    assert is_denied_path(Path.home() / "Library" / "Keychains" / "login.keychain-db")


def test_denylist_name_globs() -> None:
    assert is_denied_path(Path.home() / "projects" / "thoth" / ".env")
    assert is_denied_path(Path.home() / "projects" / "thoth" / ".env.local")
    assert is_denied_path(Path.home() / "certs" / "server.pem")
    assert is_denied_path(Path.home() / ".netrc")


def test_normal_project_path_not_denied() -> None:
    assert not is_denied_path(Path.home() / "projects" / "thoth" / "README.md")
