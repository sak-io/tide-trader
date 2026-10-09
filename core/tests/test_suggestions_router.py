import csv
import io
from datetime import UTC, datetime, timedelta

from app.models.domain import IndicatorSnapshot, Signal, SignalDirection, SignalSource


def _signal(
    symbol: str = "AAPL",
    direction: SignalDirection = SignalDirection.bullish,
    sources: list[SignalSource] | None = None,
    generated_at: datetime | None = None,
) -> Signal:
    return Signal(
        symbol=symbol,
        direction=direction,
        price=190.0,
        score=85.0,
        indicators=IndicatorSnapshot(sma_fast=105.0, sma_slow=102.0, rsi14=100.0, volume_ratio=2.7),
        triggered_rules=["golden_cross_sma20_sma50", "volume_confirmation"],
        sources=sources or [SignalSource.watchlist],
        generated_at=generated_at or datetime(2026, 9, 28, tzinfo=UTC),
    )


def test_list_defaults_to_pending_only(suggestions_api_client):
    client, store = suggestions_api_client
    store.create(_signal(symbol="AAPL"), rationale="bullish setup")
    dismissed = store.create(_signal(symbol="MSFT"), rationale=None)
    store.dismiss(dismissed.id)

    response = client.get("/api/v1/suggestions")

    assert response.status_code == 200
    assert [row["symbol"] for row in response.json()] == ["AAPL"]


def test_list_status_all_returns_everything(suggestions_api_client):
    client, store = suggestions_api_client
    store.create(_signal(symbol="AAPL"), rationale=None)
    dismissed = store.create(_signal(symbol="MSFT"), rationale=None)
    store.dismiss(dismissed.id)

    response = client.get("/api/v1/suggestions?status=all")

    assert response.status_code == 200
    assert {row["symbol"] for row in response.json()} == {"AAPL", "MSFT"}


def test_list_status_dismissed_only(suggestions_api_client):
    client, store = suggestions_api_client
    store.create(_signal(symbol="AAPL"), rationale=None)
    dismissed = store.create(_signal(symbol="MSFT"), rationale=None)
    store.dismiss(dismissed.id)

    response = client.get("/api/v1/suggestions?status=dismissed")

    assert [row["symbol"] for row in response.json()] == ["MSFT"]


def test_list_rejects_an_invalid_status(suggestions_api_client):
    client, _ = suggestions_api_client
    response = client.get("/api/v1/suggestions?status=bogus")
    assert response.status_code == 422


def test_list_filters_by_symbol(suggestions_api_client):
    client, store = suggestions_api_client
    store.create(_signal(symbol="AAPL"), rationale=None)
    store.create(_signal(symbol="MSFT"), rationale=None)

    response = client.get("/api/v1/suggestions?status=all&symbol=msft")

    assert [row["symbol"] for row in response.json()] == ["MSFT"]


def test_dismiss_flips_status_and_keeps_the_row(suggestions_api_client):
    client, store = suggestions_api_client
    created = store.create(_signal(), rationale=None)

    response = client.post(f"/api/v1/suggestions/{created.id}/dismiss")

    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"
    assert len(store.list_all()) == 1


def test_dismiss_missing_id_returns_404(suggestions_api_client):
    client, _ = suggestions_api_client
    response = client.post("/api/v1/suggestions/999/dismiss")
    assert response.status_code == 404


def test_export_returns_csv_with_expected_header_and_rows(suggestions_api_client):
    client, store = suggestions_api_client
    store.create(
        _signal(symbol="AAPL", direction=SignalDirection.bullish, sources=[SignalSource.watchlist]),
        rationale="Strong setup.",
    )
    dismissed = store.create(
        _signal(
            symbol="MSFT",
            direction=SignalDirection.bearish,
            sources=[SignalSource.watchlist, SignalSource.alpaca],
        ),
        rationale=None,
    )
    store.dismiss(dismissed.id)

    response = client.get("/api/v1/suggestions/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(response.text)))
    header, aapl_row, msft_row = rows

    assert header == [
        "id",
        "symbol",
        "direction",
        "price",
        "score",
        "stop_price",
        "target_price",
        "outcome",
        "outcome_price",
        "return_pct",
        "sma_fast",
        "sma_slow",
        "rsi14",
        "volume_ratio",
        "triggered_rules",
        "sources",
        "rationale",
        "status",
        "generated_at",
        "updated_at",
    ]

    assert aapl_row[1] == "AAPL"
    assert aapl_row[2] == "bullish"
    assert aapl_row[14] == "golden_cross_sma20_sma50;volume_confirmation"
    assert aapl_row[15] == "watchlist"
    assert aapl_row[16] == "Strong setup."
    assert aapl_row[17] == "pending"

    assert msft_row[1] == "MSFT"
    assert msft_row[2] == "bearish"
    assert msft_row[15] == "watchlist;alpaca"
    assert msft_row[16] == ""
    assert msft_row[17] == "dismissed"


def test_export_filename_reflects_all_time_by_default(suggestions_api_client):
    client, _ = suggestions_api_client
    response = client.get("/api/v1/suggestions/export")
    assert "suggestions_all.csv" in response.headers["content-disposition"]


def test_export_with_hours_only_includes_recent_rows(suggestions_api_client):
    client, store = suggestions_api_client
    now = datetime.now(UTC)
    store.create(_signal(symbol="OLD", generated_at=now - timedelta(hours=72)), rationale=None)
    store.create(_signal(symbol="RECENT", generated_at=now - timedelta(hours=2)), rationale=None)

    response = client.get("/api/v1/suggestions/export?hours=24")

    assert response.status_code == 200
    assert "suggestions_last_24h.csv" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text)))
    symbols = [row[1] for row in rows[1:]]
    assert symbols == ["RECENT"]


def test_export_rejects_non_positive_hours(suggestions_api_client):
    client, _ = suggestions_api_client
    response = client.get("/api/v1/suggestions/export?hours=0")
    assert response.status_code == 422
