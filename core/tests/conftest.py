import os
import tempfile

# Must run before `app.config`/`app.main` are imported by any test module, so the
# real Settings() picked up during FastAPI's lifespan startup never touches real
# Alpaca credentials or writes a stray SQLite file into the repo.
os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "lifespan_state.db"))
os.environ.setdefault("ALPACA_API_KEY_ID", "")
os.environ.setdefault("ALPACA_SECRET_KEY", "")
os.environ.setdefault("ALLOWED_ORIGINS", "")

import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_market_data_client,
    get_market_data_hub,
    get_risk_manager,
    get_trade_adapter,
)
from app.engine.risk_manager import RiskManager
from app.engine.state_store import StateStore
from app.main import app
from tests.fakes import FakeBarsClient, FakeMarketDataClient, FakeScreenerClient, FakeTradingClient


@pytest.fixture
def fake_trading_client() -> FakeTradingClient:
    return FakeTradingClient()


@pytest.fixture
def fake_market_data_client() -> FakeMarketDataClient:
    return FakeMarketDataClient(prices={"AAPL": 190.0, "MSFT": 300.0})


@pytest.fixture
def risk_manager(tmp_path) -> RiskManager:
    store = StateStore(tmp_path / "risk_state.db")
    return RiskManager(store, max_position_dollars=5000.0, daily_loss_limit_pct=0.03)


@pytest.fixture
def api_client(fake_trading_client, fake_market_data_client, risk_manager):
    from app.adapters.alpaca_trade import AlpacaTradeAdapter

    adapter = AlpacaTradeAdapter(fake_trading_client, fake_market_data_client)

    app.dependency_overrides[get_trade_adapter] = lambda: adapter
    app.dependency_overrides[get_risk_manager] = lambda: risk_manager

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def fake_screener_client() -> FakeScreenerClient:
    return FakeScreenerClient()


@pytest.fixture
def fake_bars_client() -> FakeBarsClient:
    return FakeBarsClient({})


@pytest.fixture
def market_api_client(fake_screener_client, fake_bars_client):
    from app.adapters.alpaca_market import AlpacaMarketDataClient

    market_client = AlpacaMarketDataClient(fake_screener_client, fake_bars_client)
    app.dependency_overrides[get_market_data_client] = lambda: market_client

    with TestClient(app) as client:
        yield client, fake_screener_client, fake_bars_client

    app.dependency_overrides.clear()


@pytest.fixture
def stream_client():
    from app.adapters.alpaca_data import MarketDataHub

    hub = MarketDataHub()
    app.dependency_overrides[get_market_data_hub] = lambda: hub

    with TestClient(app) as client:
        yield client, hub

    app.dependency_overrides.clear()
