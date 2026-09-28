import json

from alpaca.common.exceptions import APIError

from app.main import app
from app.routers.alpaca_connection import get_credential_prober


class _FakeProbeAdapter:
    def __init__(self, should_fail: bool, failure_message: str = "invalid credentials"):
        self._should_fail = should_fail
        self._failure_message = failure_message

    def get_account(self):
        if self._should_fail:
            raise APIError(json.dumps({"code": 40110000, "message": self._failure_message}))
        return None


def _override_prober(should_fail: bool, failure_message: str = "invalid credentials"):
    """Returns a zero-argument FastAPI dependency-provider (matching the shape of the
    real `get_credential_prober`), which in turn returns the fake 3-arg prober
    callable the route actually invokes."""

    def factory(api_key_id: str, secret_key: str, paper: bool):
        return _FakeProbeAdapter(should_fail, failure_message)

    return lambda: factory


def test_status_is_disconnected_before_any_connect(alpaca_connection_client):
    response = alpaca_connection_client.get("/api/v1/alpaca/status")

    assert response.status_code == 200
    assert response.json() == {"connected": False}


def test_connect_success_flips_status_to_connected(alpaca_connection_client):
    app.dependency_overrides[get_credential_prober] = _override_prober(should_fail=False)

    response = alpaca_connection_client.post(
        "/api/v1/alpaca/connect", json={"api_key_id": "PKTEST", "secret_key": "supersecret"}
    )

    assert response.status_code == 200
    assert response.json() == {"connected": True}

    status_response = alpaca_connection_client.get("/api/v1/alpaca/status")
    assert status_response.json() == {"connected": True}


def test_connect_failure_returns_400_with_alpaca_rejection_reason(alpaca_connection_client):
    app.dependency_overrides[get_credential_prober] = _override_prober(
        should_fail=True, failure_message="access key verification failed"
    )

    secret = "top-secret-value-should-never-leak"
    response = alpaca_connection_client.post(
        "/api/v1/alpaca/connect", json={"api_key_id": "PKBAD", "secret_key": secret}
    )

    assert response.status_code == 400
    assert "access key verification failed" in response.json()["detail"]
    assert secret not in response.text

    # A failed connect must not have flipped the global connection state.
    status_response = alpaca_connection_client.get("/api/v1/alpaca/status")
    assert status_response.json() == {"connected": False}


def test_connect_failure_never_echoes_the_raw_secret_even_if_alpaca_did(alpaca_connection_client):
    secret = "leak-me-not-0123456789"
    app.dependency_overrides[get_credential_prober] = _override_prober(
        should_fail=True, failure_message=f"rejected secret {secret}"
    )

    response = alpaca_connection_client.post(
        "/api/v1/alpaca/connect", json={"api_key_id": "PKBAD", "secret_key": secret}
    )

    assert response.status_code == 400
    assert secret not in response.text


def test_connect_failure_falls_back_to_raw_string_when_alpaca_error_is_not_json(alpaca_connection_client):
    class _RawErrorProbeAdapter:
        def get_account(self):
            raise APIError("not valid json")

    def build_prober():
        return lambda *args, **kwargs: _RawErrorProbeAdapter()

    app.dependency_overrides[get_credential_prober] = build_prober

    response = alpaca_connection_client.post(
        "/api/v1/alpaca/connect", json={"api_key_id": "PKBAD", "secret_key": "whatever"}
    )

    assert response.status_code == 400
    assert "not valid json" in response.json()["detail"]


def test_disconnect_clears_connection(alpaca_connection_client):
    app.dependency_overrides[get_credential_prober] = _override_prober(should_fail=False)
    alpaca_connection_client.post(
        "/api/v1/alpaca/connect", json={"api_key_id": "PKTEST", "secret_key": "supersecret"}
    )

    response = alpaca_connection_client.delete("/api/v1/alpaca/disconnect")
    assert response.status_code == 204

    status_response = alpaca_connection_client.get("/api/v1/alpaca/status")
    assert status_response.json() == {"connected": False}


def test_connect_rejects_empty_api_key_id(alpaca_connection_client):
    response = alpaca_connection_client.post(
        "/api/v1/alpaca/connect", json={"api_key_id": "", "secret_key": "supersecret"}
    )
    assert response.status_code == 422


def test_connect_rejects_empty_secret_key(alpaca_connection_client):
    response = alpaca_connection_client.post(
        "/api/v1/alpaca/connect", json={"api_key_id": "PKTEST", "secret_key": ""}
    )
    assert response.status_code == 422
