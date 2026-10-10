from types import SimpleNamespace

import pytest

from app.adapters.alpaca_trade import AlpacaTradeAdapter
from app.models.domain import OrderRequest, OrderSide, OrderStatus, OrderType
from tests.fakes import FakeMarketDataClient, FakeTradingClient


def make_adapter(
    equity=10000.0, last_equity=10100.0, prices=None
) -> tuple[AlpacaTradeAdapter, FakeTradingClient]:
    trading_client = FakeTradingClient(equity=equity, last_equity=last_equity)
    market_client = FakeMarketDataClient(prices or {"AAPL": 190.0})
    return AlpacaTradeAdapter(trading_client, market_client), trading_client


def test_get_account_computes_daily_pl():
    adapter, _ = make_adapter(equity=10000.0, last_equity=10100.0)

    summary = adapter.get_account()

    assert summary.equity == 10000.0
    assert summary.daily_pl == pytest.approx(-100.0)
    assert summary.daily_pl_pct == pytest.approx(-100.0 / 10100.0)


def test_get_latest_price_looks_up_by_symbol():
    adapter, _ = make_adapter(prices={"AAPL": 123.45})
    assert adapter.get_latest_price("AAPL") == 123.45


def test_submit_market_order_maps_response_fields():
    adapter, client = make_adapter()
    order = OrderRequest(symbol="aapl", qty=1, side=OrderSide.buy, order_type=OrderType.market)

    response = adapter.submit_order(order)

    assert response.symbol == "AAPL"
    assert response.side == OrderSide.buy
    assert response.order_type == OrderType.market
    assert response.status == OrderStatus.accepted
    assert response.id in client.orders


def test_submit_limit_order_maps_limit_order_type():
    adapter, _ = make_adapter()
    order = OrderRequest(
        symbol="MSFT", qty=2, side=OrderSide.sell, order_type=OrderType.limit, limit_price=300.0
    )

    response = adapter.submit_order(order)

    assert response.order_type == OrderType.limit
    assert response.side == OrderSide.sell


def test_cancel_order_delegates_to_client():
    adapter, client = make_adapter()

    adapter.cancel_order("order-1")

    assert "order-1" in client.canceled


def test_get_order_maps_response():
    adapter, client = make_adapter()
    order = OrderRequest(symbol="AAPL", qty=1, side=OrderSide.buy, order_type=OrderType.market)
    submitted = adapter.submit_order(order)

    fetched = adapter.get_order(submitted.id)

    assert fetched.id == submitted.id
    assert fetched.symbol == "AAPL"


def test_get_positions_maps_fields():
    adapter, client = make_adapter()
    client.positions = [
        SimpleNamespace(
            symbol="AAPL",
            qty="10",
            avg_entry_price="150.0",
            market_value="1900.0",
            current_price="190.0",
            unrealized_pl="400.0",
            unrealized_plpc="0.2667",
        )
    ]

    positions = adapter.get_positions()

    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].qty == 10.0
    assert positions[0].unrealized_pl == 400.0


def test_get_positions_empty_when_no_positions():
    adapter, _ = make_adapter()
    assert adapter.get_positions() == []


def test_from_credentials_constructs_real_clients_without_hitting_network():
    adapter = AlpacaTradeAdapter.from_credentials("key", "secret", paper=True)

    assert isinstance(adapter, AlpacaTradeAdapter)
