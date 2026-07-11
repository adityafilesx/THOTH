from thoth_daemon.security.redaction import REDACTED, redact


def test_redacts_secret_keys_case_insensitive() -> None:
    data = {
        "password": "p",
        "API_KEY": "k",
        "Authorization": "Bearer x",
        "nested": {"client_secret": "s", "ok": 1},
        "safe": "visible",
    }
    out = redact(data)
    assert out["password"] == REDACTED
    assert out["API_KEY"] == REDACTED
    assert out["Authorization"] == REDACTED
    assert out["nested"]["client_secret"] == REDACTED
    assert out["nested"]["ok"] == 1
    assert out["safe"] == "visible"


def test_redacts_inside_lists_and_leaves_input_unmodified() -> None:
    data = {"items": [{"token": "t1"}, {"token": "t2"}, "plain"]}
    out = redact(data)
    assert [i["token"] for i in out["items"][:2]] == [REDACTED, REDACTED]
    assert out["items"][2] == "plain"
    assert data["items"][0]["token"] == "t1"  # original untouched


def test_extra_fields_parameter() -> None:
    out = redact({"recipient": "a@b.c", "body": "hi", "x": 1}, extra_fields=["recipient", "body"])
    assert out["recipient"] == REDACTED
    assert out["body"] == REDACTED
    assert out["x"] == 1


def test_non_dict_passthrough() -> None:
    assert redact("plain") == "plain"
    assert redact(42) == 42
    assert redact([1, 2]) == [1, 2]
