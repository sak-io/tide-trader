from types import SimpleNamespace


def test_get_most_active_returns_mapped_tickers(market_api_client):
    client, screener, _ = market_api_client
    screener._most_actives = SimpleNamespace(
        most_actives=[SimpleNamespace(symbol="AAPL", volume=1_000_000.0, trade_count=5000.0)]
    )

    response = client.get("/api/v1/market/most-active?top=5")

    assert response.status_code == 200
    body = response.json()
    assert body == [{"symbol": "AAPL", "volume": 1_000_000.0, "trade_count": 5000.0}]


def test_get_most_active_rejects_out_of_range_top(market_api_client):
    client, _, _ = market_api_client
    response = client.get("/api/v1/market/most-active?top=0")
    assert response.status_code == 422


def test_get_movers_returns_gainers_and_losers(market_api_client):
    client, screener, _ = market_api_client
    screener._movers = SimpleNamespace(
        gainers=[SimpleNamespace(symbol="NVDA", percent_change=5.2, change=10.0, price=200.0)],
        losers=[SimpleNamespace(symbol="INTC", percent_change=-3.1, change=-1.5, price=45.0)],
    )

    response = client.get("/api/v1/market/movers?top=5")

    assert response.status_code == 200
    body = response.json()
    assert body["gainers"][0]["symbol"] == "NVDA"
    assert body["losers"][0]["symbol"] == "INTC"


def test_get_bars_returns_historical_data(market_api_client):
    client, _, bars_client = market_api_client
    bars_client.bars_by_symbol = {
        "AAPL": [
            SimpleNamespace(
                timestamp="2026-09-25T00:00:00Z",
                open=190.0,
                high=191.0,
                low=189.0,
                close=190.5,
                volume=1000.0,
            )
        ]
    }

    response = client.get("/api/v1/market/bars/AAPL?timeframe=1Day")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["close"] == 190.5


def test_get_bars_returns_400_for_unsupported_timeframe(market_api_client):
    client, _, _ = market_api_client
    response = client.get("/api/v1/market/bars/AAPL?timeframe=3Weeks")

    assert response.status_code == 400
    assert "Unsupported timeframe" in response.json()["detail"]


def test_get_bars_empty_for_symbol_with_no_data(market_api_client):
    client, _, bars_client = market_api_client
    bars_client.bars_by_symbol = {}

    response = client.get("/api/v1/market/bars/ZZZZ")

    assert response.status_code == 200
    assert response.json() == []
