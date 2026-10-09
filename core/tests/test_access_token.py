import os
import stat
import subprocess
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


@pytest.fixture
def windows(monkeypatch):
    """Pretend to be Windows, with a recording fake `icacls` instead of the real one."""
    calls = []
    outcome = {"error": None}

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if outcome["error"]:
            raise outcome["error"]
        return SimpleNamespace(returncode=0)

    fake_subprocess = SimpleNamespace(run=fake_run, SubprocessError=subprocess.SubprocessError)
    monkeypatch.setattr(access_token_module, "_IS_WINDOWS", True)
    monkeypatch.setattr(access_token_module, "subprocess", fake_subprocess)
    monkeypatch.setattr(access_token_module.getpass, "getuser", lambda: "alice")
    return SimpleNamespace(calls=calls, outcome=outcome)


def _home(monkeypatch, home):
    monkeypatch.setattr(access_token_module.Path, "home", classmethod(lambda cls: home))


def test_windows_restricts_token_with_icacls_and_does_not_chmod(tmp_path, windows, monkeypatch):
    target = tmp_path / "file"
    target.write_text("x", encoding="utf-8")
    mode_before = stat.S_IMODE(target.stat().st_mode)

    access_token_module._restrict_to_owner(target)

    assert windows.calls == [["icacls", str(target), "/inheritance:r", "/grant:r", "alice:F"]]
    assert stat.S_IMODE(target.stat().st_mode) == mode_before


def test_windows_icacls_success_emits_no_warning(tmp_path, windows, monkeypatch, caplog):
    target = tmp_path / "file"
    target.write_text("x", encoding="utf-8")
    _home(monkeypatch, tmp_path / "home")  # outside home, but hardened, so no warning

    with caplog.at_level("WARNING"):
        access_token_module._restrict_to_owner(target)

    assert caplog.text == ""


def test_windows_icacls_failure_outside_home_warns(tmp_path, windows, monkeypatch, caplog):
    target = tmp_path / "my dir" / "file"
    target.parent.mkdir()
    target.write_text("x", encoding="utf-8")
    _home(monkeypatch, tmp_path / "home")
    windows.outcome["error"] = FileNotFoundError("icacls not found")

    with caplog.at_level("WARNING"):
        access_token_module._restrict_to_owner(target)

    assert "Could not restrict" in caplog.text
    assert "outside your user profile" in caplog.text
    # `%%` must render as a single `%`, and the path must be quoted for spaces.
    assert f'icacls "{target}" /inheritance:r /grant:r "%USERNAME%:F"' in caplog.text
    assert "keep it under %USERPROFILE%" in caplog.text


def test_windows_icacls_failure_inside_home_only_logs_the_failure(tmp_path, windows, monkeypatch, caplog):
    target = tmp_path / "file"
    target.write_text("x", encoding="utf-8")
    _home(monkeypatch, tmp_path)
    windows.outcome["error"] = subprocess.CalledProcessError(5, "icacls")

    with caplog.at_level("WARNING"):
        access_token_module._restrict_to_owner(target)

    assert "Could not restrict" in caplog.text
    assert "outside your user profile" not in caplog.text


def test_windows_token_is_created_and_hardened_then_reused_and_rehardened(tmp_path, windows):
    token_path = tmp_path / "access-token"

    token = load_or_create_access_token(token_path)
    assert len(windows.calls) == 1

    assert load_or_create_access_token(token_path) == token
    assert len(windows.calls) == 2  # idempotent re-apply on reuse (tightens old tokens)
    assert token_path.read_text(encoding="utf-8") == token


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_token_file_is_never_created_world_readable(tmp_path, monkeypatch):
    # Created with 0o600 up front, not chmod'd afterwards: no-op the chmod to prove it.
    monkeypatch.setattr(access_token_module.os, "chmod", lambda p, m: None)
    old_umask = os.umask(0o000)  # worst case: umask would otherwise allow 0o666
    try:
        token_path = tmp_path / "access-token"
        load_or_create_access_token(token_path)
    finally:
        os.umask(old_umask)

    assert stat.S_IMODE(token_path.stat().st_mode) == 0o600


def test_existing_file_is_not_overwritten_or_followed(tmp_path):
    token_path = tmp_path / "access-token"
    token_path.write_text("existing", encoding="utf-8")

    assert load_or_create_access_token(token_path) == "existing"


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
