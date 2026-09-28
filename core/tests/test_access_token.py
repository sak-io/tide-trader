import stat
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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


def test_token_file_is_created_with_owner_only_permissions(tmp_path):
    token_path = tmp_path / "access-token"

    load_or_create_access_token(token_path)

    mode = stat.S_IMODE(token_path.stat().st_mode)
    assert mode == 0o600


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
