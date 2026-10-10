import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest

from app.engine.suggestion_store import SuggestionStore
from app.models.domain import (
    IndicatorSnapshot,
    Signal,
    SignalDirection,
    SignalSource,
    SuggestionStatus,
)


def _signal(
    symbol: str = "AAPL",
    direction: SignalDirection = SignalDirection.bullish,
    generated_at: datetime | None = None,
    sources: list[SignalSource] | None = None,
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


def test_create_persists_and_returns_a_pending_suggestion(tmp_path):
    store = SuggestionStore(tmp_path / "suggestions.db")

    suggestion = store.create(_signal(), rationale="Looks strong.")

    assert suggestion.id is not None
    assert suggestion.symbol == "AAPL"
    assert suggestion.direction == SignalDirection.bullish
    assert suggestion.status == SuggestionStatus.pending
    assert suggestion.rationale == "Looks strong."
    assert suggestion.sources == [SignalSource.watchlist]
    assert suggestion.indicators.sma_fast == 105.0
    assert suggestion.triggered_rules == ["golden_cross_sma20_sma50", "volume_confirmation"]


def test_create_keeps_both_directions_for_the_same_symbol_and_day(tmp_path):
    store = SuggestionStore(tmp_path / "suggestions.db")
    same_day = datetime(2026, 9, 28, tzinfo=UTC)

    store.create(_signal(generated_at=same_day), rationale=None)
    store.create(_signal(direction=SignalDirection.bearish, generated_at=same_day), rationale=None)

    assert len(store.list_all()) == 2


def test_database_rejects_a_duplicate_symbol_direction_bar(tmp_path):
    store = SuggestionStore(tmp_path / "suggestions.db")
    signal = _signal(generated_at=datetime(2026, 9, 28, tzinfo=UTC))

    store.create(signal, rationale=None)
    with pytest.raises(sqlite3.IntegrityError):
        store.create(signal, rationale=None)


def test_dedupe_is_keyed_on_the_bar_date_not_the_wall_clock(tmp_path):
    store = SuggestionStore(tmp_path / "suggestions.db")
    friday_bar = date(2026, 9, 25)
    friday_night = _signal(generated_at=datetime(2026, 9, 26, 1, tzinfo=UTC))
    friday_night.bar_date = friday_bar

    store.create(friday_night, rationale=None)

    # Re-detected on Sunday from the same Friday bar: same key, so it is a duplicate.
    assert store.exists_for_day("AAPL", "bullish", friday_bar.isoformat()) is True
    assert store.list_all()[0].bar_date == friday_bar


def test_exists_for_today_reflects_the_dedupe_key(tmp_path):
    store = SuggestionStore(tmp_path / "suggestions.db")
    today = date(2026, 9, 28).isoformat()
    signal = _signal(generated_at=datetime(2026, 9, 28, tzinfo=UTC))

    assert store.exists_for_day("AAPL", "bullish", today) is False

    store.create(signal, rationale=None)

    assert store.exists_for_day("AAPL", "bullish", today) is True
    assert store.exists_for_day("aapl", "bullish", today) is True
    assert store.exists_for_day("AAPL", "bearish", today) is False
    assert store.exists_for_day("MSFT", "bullish", today) is False


def test_list_pending_excludes_dismissed(tmp_path):
    store = SuggestionStore(tmp_path / "suggestions.db")
    pending = store.create(_signal(symbol="AAPL"), rationale=None)
    dismissed = store.create(_signal(symbol="MSFT"), rationale=None)
    store.dismiss(dismissed.id)

    result = store.list_pending()

    assert [s.id for s in result] == [pending.id]


def test_list_all_filters_by_symbol_case_insensitively(tmp_path):
    store = SuggestionStore(tmp_path / "suggestions.db")
    store.create(_signal(symbol="AAPL"), rationale=None)
    store.create(_signal(symbol="MSFT"), rationale=None)

    result = store.list_all(symbol="msft")

    assert [s.symbol for s in result] == ["MSFT"]


def test_list_all_orders_by_generated_at_then_id(tmp_path):
    store = SuggestionStore(tmp_path / "suggestions.db")
    first_signal = _signal(symbol="AAPL", generated_at=datetime(2026, 9, 1, tzinfo=UTC))
    second_signal = _signal(symbol="MSFT", generated_at=datetime(2026, 9, 2, tzinfo=UTC))
    first = store.create(first_signal, rationale=None)
    second = store.create(second_signal, rationale=None)

    result = store.list_all()

    assert [s.id for s in result] == [first.id, second.id]


def test_dismiss_flips_status_but_keeps_the_row(tmp_path):
    store = SuggestionStore(tmp_path / "suggestions.db")
    created = store.create(_signal(), rationale=None)

    dismissed = store.dismiss(created.id)

    assert dismissed is not None
    assert dismissed.status == SuggestionStatus.dismissed
    assert len(store.list_all()) == 1


def test_dismiss_missing_id_returns_none(tmp_path):
    store = SuggestionStore(tmp_path / "suggestions.db")
    assert store.dismiss(999) is None


def test_list_all_filters_by_since(tmp_path):
    store = SuggestionStore(tmp_path / "suggestions.db")
    now = datetime.now(UTC)
    old = store.create(_signal(symbol="AAPL", generated_at=now - timedelta(hours=48)), rationale=None)
    recent = store.create(_signal(symbol="MSFT", generated_at=now - timedelta(hours=1)), rationale=None)

    result = store.list_all(since=now - timedelta(hours=24))

    assert [s.id for s in result] == [recent.id]
    assert old.id not in [s.id for s in result]


def test_sources_round_trip_preserves_multiple_tags(tmp_path):
    store = SuggestionStore(tmp_path / "suggestions.db")
    store.create(_signal(sources=[SignalSource.watchlist, SignalSource.alpaca]), rationale=None)

    fetched = store.list_all()[0]

    assert set(fetched.sources) == {SignalSource.watchlist, SignalSource.alpaca}
