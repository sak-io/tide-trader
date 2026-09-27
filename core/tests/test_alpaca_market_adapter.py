from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from alpaca.data.enums import DataFeed
from alpaca.data.timeframe import TimeFrameUnit

from app.adapters.alpaca_market import AlpacaMarketDataClient, parse_timeframe
from tests.fakes import FakeBarsClient, FakeScreenerClient


def make_client(most_actives=None, movers=None, bars=None):
    screener = FakeScreenerClient(most_actives=most_actives, movers=movers)
    bars_client = FakeBarsClient(bars or {})
    return AlpacaMarketDataClient(screener, bars_client), bars_client


def test_get_most_active_maps_fields():
    most_actives = SimpleNamespace(
        most_actives=[SimpleNamespace(symbol="AAPL", volume=1_000_000.0, trade_count=5000.0)]
    )
    client, _ = make_client(most_actives=most_actives)

    result = client.get_most_active(top=5)

    assert len(result) == 1
    assert result[0].symbol == "AAPL"
    assert result[0].volume == 1_000_000.0
    assert result[0].trade_count == 5000.0


def test_get_movers_maps_gainers_and_losers():
    movers = SimpleNamespace(
        gainers=[SimpleNamespace(symbol="NVDA", percent_change=5.2, change=10.0, price=200.0)],
        losers=[SimpleNamespace(symbol="INTC", percent_change=-3.1, change=-1.5, price=45.0)],
    )
    client, _ = make_client(movers=movers)

    result = client.get_movers(top=5)

    assert result.gainers[0].symbol == "NVDA"
    assert result.gainers[0].percent_change == 5.2
    assert result.losers[0].symbol == "INTC"
    assert result.losers[0].change == -1.5


def test_get_bars_maps_fields_and_uppercases_symbol():
    now = datetime.now(timezone.utc)
    bars = {
        "AAPL": [
            SimpleNamespace(timestamp=now, open=190.0, high=191.0, low=189.0, close=190.5, volume=1000.0),
        ]
    }
    client, bars_client = make_client(bars=bars)

    result = client.get_bars("aapl", timeframe="1Day")

    assert len(result) == 1
    assert result[0].close == 190.5
    assert result[0].timestamp == now
    assert bars_client.last_request.symbol_or_symbols == "AAPL"
    assert bars_client.last_request.feed == DataFeed.IEX


def test_get_bars_returns_empty_list_for_unknown_symbol():
    client, _ = make_client(bars={})
    assert client.get_bars("ZZZZ") == []


def test_get_bars_rejects_unsupported_timeframe():
    client, _ = make_client(bars={})
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        client.get_bars("AAPL", timeframe="3Weeks")


def test_parse_timeframe_supports_known_presets():
    timeframe = parse_timeframe("1Day")
    assert timeframe.amount == 1
    assert timeframe.unit == TimeFrameUnit.Day

    timeframe = parse_timeframe("15Min")
    assert timeframe.amount == 15
    assert timeframe.unit == TimeFrameUnit.Minute


def test_parse_timeframe_rejects_unsupported_value():
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        parse_timeframe("3Weeks")
