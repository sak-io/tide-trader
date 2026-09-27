from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings


class FakeRunner:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


def test_lifespan_starts_and_stops_the_stream_runner_when_credentials_are_configured(monkeypatch, tmp_path):
    fake_runner = FakeRunner()

    dummy_settings = Settings(
        alpaca_api_key_id="key",
        alpaca_secret_key="secret",
        db_path=str(tmp_path / "state.db"),
    )

    monkeypatch.setattr(main_module, "get_settings", lambda: dummy_settings)
    monkeypatch.setattr(main_module, "build_stream_runner", lambda settings, hub: fake_runner)

    app = main_module.create_app()

    with TestClient(app):
        assert fake_runner.started is True

    assert fake_runner.stopped is True


def test_lifespan_skips_stream_runner_without_credentials(tmp_path, monkeypatch):
    dummy_settings = Settings(
        alpaca_api_key_id="",
        alpaca_secret_key="",
        db_path=str(tmp_path / "state.db"),
    )
    monkeypatch.setattr(main_module, "get_settings", lambda: dummy_settings)

    app = main_module.create_app()

    with TestClient(app):
        assert app.state.stream_runner is None
        assert app.state.trade_adapter is None


def test_routes_return_503_instead_of_crashing_without_credentials(tmp_path, monkeypatch):
    """Before Alpaca keys are configured, every route that needs them must fail
    cleanly rather than raising an unguarded AttributeError on a None adapter."""
    dummy_settings = Settings(
        alpaca_api_key_id="",
        alpaca_secret_key="",
        db_path=str(tmp_path / "state.db"),
    )
    monkeypatch.setattr(main_module, "get_settings", lambda: dummy_settings)

    app = main_module.create_app()

    with TestClient(app, raise_server_exceptions=False) as client:
        for response in (
            client.get("/api/v1/account"),
            client.get("/api/v1/positions"),
            client.get("/api/v1/market/most-active"),
            client.get("/api/v1/market/movers"),
            client.get("/api/v1/market/bars/AAPL"),
            client.post("/api/v1/orders", json={"symbol": "AAPL", "qty": 1, "side": "buy"}),
        ):
            assert response.status_code == 503
            assert "not configured" in response.json()["detail"]
