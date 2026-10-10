import asyncio

from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.security.alpaca_session import AlpacaConnection


class FakeRunner:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


def test_lifespan_starts_and_stops_a_configured_stream_runner(monkeypatch, tmp_path):
    """build_stream_runner always returns None today (see its docstring), but the
    lifespan itself must still correctly start/stop whatever it's handed - exercised
    here by monkeypatching build_stream_runner, the same seam a future real
    implementation would use."""
    fake_runner = FakeRunner()

    dummy_settings = Settings(db_path=str(tmp_path / "state.db"))

    monkeypatch.setattr(main_module, "get_settings", lambda: dummy_settings)
    monkeypatch.setattr(main_module, "build_stream_runner", lambda settings, hub: fake_runner)

    app = main_module.create_app()

    with TestClient(app):
        assert fake_runner.started is True

    assert fake_runner.stopped is True


def test_lifespan_has_no_stream_runner_by_default(tmp_path, monkeypatch):
    dummy_settings = Settings(db_path=str(tmp_path / "state.db"))
    monkeypatch.setattr(main_module, "get_settings", lambda: dummy_settings)

    app = main_module.create_app()

    with TestClient(app):
        assert app.state.stream_runner is None


def test_lifespan_wires_access_token_and_alpaca_connection(tmp_path, monkeypatch):
    dummy_settings = Settings(db_path=str(tmp_path / "state.db"))
    monkeypatch.setattr(main_module, "get_settings", lambda: dummy_settings)

    app = main_module.create_app()

    with TestClient(app):
        assert isinstance(app.state.access_token, str)
        assert len(app.state.access_token) > 20
        assert isinstance(app.state.alpaca_connection, AlpacaConnection)
        assert app.state.alpaca_connection.is_connected() is False


def test_routes_return_503_instead_of_crashing_without_an_alpaca_connection(tmp_path, monkeypatch):
    """Before an Alpaca account is connected, every route that needs it must fail
    cleanly rather than raising an unguarded AttributeError on a None session."""
    dummy_settings = Settings(db_path=str(tmp_path / "state.db"))
    monkeypatch.setattr(main_module, "get_settings", lambda: dummy_settings)

    app = main_module.create_app()

    with TestClient(app, raise_server_exceptions=False) as client:
        token = app.state.access_token
        headers = {"Authorization": f"Bearer {token}"}

        for response in (
            client.get("/api/v1/account", headers=headers),
            client.get("/api/v1/positions", headers=headers),
            client.get("/api/v1/market/most-active", headers=headers),
            client.get("/api/v1/market/movers", headers=headers),
            client.get("/api/v1/market/bars/AAPL", headers=headers),
            client.post("/api/v1/orders", json={"symbol": "AAPL", "qty": 1, "side": "buy"}, headers=headers),
        ):
            assert response.status_code == 503
            assert "not connected" in response.json()["detail"]


def test_routes_return_401_without_a_valid_access_token(tmp_path, monkeypatch):
    dummy_settings = Settings(db_path=str(tmp_path / "state.db"))
    monkeypatch.setattr(main_module, "get_settings", lambda: dummy_settings)

    app = main_module.create_app()

    with TestClient(app, raise_server_exceptions=False) as client:
        for response in (
            client.get("/api/v1/account"),
            client.get("/api/v1/positions"),
            client.get("/api/v1/market/most-active"),
            client.post("/api/v1/orders", json={"symbol": "AAPL", "qty": 1, "side": "buy"}),
            client.get("/api/v1/alpaca/status"),
            client.get("/api/v1/suggestions"),
            client.get("/api/v1/watchlist"),
        ):
            assert response.status_code == 401


class FakeScanLoop:
    def __init__(self, *args, **kwargs):
        del args, kwargs
        self.run_forever_called = False
        self.cancelled = False

    async def run_forever(self) -> None:
        self.run_forever_called = True
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def test_lifespan_starts_and_stops_the_suggestion_scan_loop_when_enabled(tmp_path, monkeypatch):
    dummy_settings = Settings(db_path=str(tmp_path / "state.db"), enable_suggestion_scanner=True)
    monkeypatch.setattr(main_module, "get_settings", lambda: dummy_settings)

    created_loops: list[FakeScanLoop] = []

    def fake_scan_loop_factory(*args, **kwargs):
        loop = FakeScanLoop(*args, **kwargs)
        created_loops.append(loop)
        return loop

    monkeypatch.setattr(main_module, "SuggestionScanLoop", fake_scan_loop_factory)

    app = main_module.create_app()

    with TestClient(app):
        assert len(created_loops) == 1
        assert created_loops[0].run_forever_called is True

    assert created_loops[0].cancelled is True


def test_lifespan_does_not_start_the_suggestion_scan_loop_when_disabled(tmp_path, monkeypatch):
    dummy_settings = Settings(db_path=str(tmp_path / "state.db"), enable_suggestion_scanner=False)
    monkeypatch.setattr(main_module, "get_settings", lambda: dummy_settings)

    created_loops: list[FakeScanLoop] = []

    def fake_scan_loop_factory(*args, **kwargs):
        loop = FakeScanLoop(*args, **kwargs)
        created_loops.append(loop)
        return loop

    monkeypatch.setattr(main_module, "SuggestionScanLoop", fake_scan_loop_factory)

    app = main_module.create_app()

    with TestClient(app):
        pass

    # The loop object is still constructed (cheap, no I/O) - only starting it as a
    # background task is gated on enable_suggestion_scanner.
    assert len(created_loops) == 1
    assert created_loops[0].run_forever_called is False
