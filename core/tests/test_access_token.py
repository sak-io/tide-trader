import stat
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.security import access_token as access_token_module
from app.security.access_token import load_or_create_access_token, require_access_token


def test_generates_a_new_token_when_file_is_missing(tmp_path):
    token_path = tmp_path / "access-token"
    assert not token_path.exists()

    token = load_or_create_access_token(token_path)

    assert token_path.exists()
    assert len(token) > 20


def test_reuses_the_same_token_on_subsequent_calls(tmp_path):
    token_path = tmp_path / "access-token"

    first = load_or_create_access_token(token_path)
    second = load_or_create_access_token(token_path)

    assert first == second


@pytest.mark.skipif(sys.platform == "win32", reason="Windows uses NTFS ACLs, not POSIX permission bits")
def test_token_file_is_created_with_owner_only_permissions(tmp_path):
    token_path = tmp_path / "access-token"

    load_or_create_access_token(token_path)

    mode = stat.S_IMODE(token_path.stat().st_mode)
    assert mode == 0o600


def test_restrict_to_owner_skips_chmod_on_windows(tmp_path, monkeypatch):
    target = tmp_path / "file"
    target.write_text("x", encoding="utf-8")
    mode_before = stat.S_IMODE(target.stat().st_mode)
    monkeypatch.setattr(access_token_module, "_IS_WINDOWS", True)

    access_token_module._restrict_to_owner(target)

    # Untouched: no chmod happens on the Windows branch.
    assert stat.S_IMODE(target.stat().st_mode) == mode_before


def test_restrict_to_owner_warns_on_windows_outside_home(tmp_path, monkeypatch, caplog):
    target = tmp_path / "file"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(access_token_module, "_IS_WINDOWS", True)
    monkeypatch.setattr(access_token_module.Path, "home", classmethod(lambda cls: tmp_path / "home"))

    with caplog.at_level("WARNING"):
        access_token_module._restrict_to_owner(target)

    assert "outside your user profile" in caplog.text


def test_warning_text_formats_icacls_hint_correctly(tmp_path, monkeypatch, caplog):
    target = tmp_path / "my dir" / "file"
    target.parent.mkdir()
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(access_token_module, "_IS_WINDOWS", True)
    monkeypatch.setattr(access_token_module.Path, "home", classmethod(lambda cls: tmp_path / "home"))

    with caplog.at_level("WARNING"):
        access_token_module._restrict_to_owner(target)

    assert f'icacls "{target}" /inheritance:r /grant:r "%USERNAME%:F"' in caplog.text
    assert "keep it under %USERPROFILE%" in caplog.text


def test_existing_token_outside_home_still_warns_on_windows(tmp_path, monkeypatch, caplog):
    target = tmp_path / "access-token"
    target.write_text("tok", encoding="utf-8")
    monkeypatch.setattr(access_token_module, "_IS_WINDOWS", True)
    monkeypatch.setattr(access_token_module.Path, "home", classmethod(lambda cls: tmp_path / "home"))

    with caplog.at_level("WARNING"):
        assert load_or_create_access_token(target) == "tok"

    assert "outside your user profile" in caplog.text


def test_restrict_to_owner_silent_on_windows_inside_home(tmp_path, monkeypatch, caplog):
    target = tmp_path / "file"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(access_token_module, "_IS_WINDOWS", True)
    monkeypatch.setattr(access_token_module.Path, "home", classmethod(lambda cls: tmp_path))

    with caplog.at_level("WARNING"):
        access_token_module._restrict_to_owner(target)

    assert caplog.text == ""


def test_token_is_created_and_reused_when_running_as_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(access_token_module, "_IS_WINDOWS", True)
    token_path = tmp_path / "access-token"

    token = load_or_create_access_token(token_path)

    assert token_path.read_text(encoding="utf-8") == token
    assert load_or_create_access_token(token_path) == token


def test_creates_parent_directories_if_needed(tmp_path):
    token_path = tmp_path / "nested" / "dir" / "access-token"

    load_or_create_access_token(token_path)

    assert token_path.exists()


def test_default_path_resolution_honors_env_var_override(tmp_path, monkeypatch):
    token_path = tmp_path / "override-token"
    monkeypatch.setenv("TIDE_TRADER_ACCESS_TOKEN_PATH", str(token_path))

    token = load_or_create_access_token()

    assert token_path.exists()
    assert load_or_create_access_token() == token


def _fake_request(access_token: str, header_value: str | None) -> SimpleNamespace:
    headers = {"Authorization": header_value} if header_value is not None else {}
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(access_token=access_token)),
        headers=headers,
    )


def test_require_access_token_raises_401_when_header_missing():
    request = _fake_request("expected-token", None)

    with pytest.raises(HTTPException) as exc_info:
        require_access_token(request)

    assert exc_info.value.status_code == 401


def test_require_access_token_raises_401_for_wrong_scheme():
    request = _fake_request("expected-token", "Basic expected-token")

    with pytest.raises(HTTPException) as exc_info:
        require_access_token(request)

    assert exc_info.value.status_code == 401


def test_require_access_token_raises_401_for_wrong_token():
    request = _fake_request("expected-token", "Bearer wrong-token")

    with pytest.raises(HTTPException) as exc_info:
        require_access_token(request)

    assert exc_info.value.status_code == 401


def test_require_access_token_passes_for_correct_token():
    request = _fake_request("expected-token", "Bearer expected-token")

    assert require_access_token(request) is None
