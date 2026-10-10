import sqlite3
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from app.engine.monitor import SuggestionMonitor, evaluate
from app.engine.screener import ScanCandidate, atr, detect_crossover_signal
from app.engine.suggestion_store import SuggestionStore
from app.models.domain import (
    HistoricalBar,
    IndicatorSnapshot,
    Signal,
    SignalDirection,
    SignalSource,
    Suggestion,
    SuggestionOutcome,
    SuggestionStatus,
)
from tests.fakes import FakeAlpacaConnection, crossover_bars

DAY0 = datetime(2026, 9, 1, tzinfo=UTC)


def _bar(day: int, low: float, high: float, close: float | None = None) -> HistoricalBar:
    close = close if close is not None else (low + high) / 2
    return HistoricalBar(
        timestamp=DAY0 + timedelta(days=day), open=close, high=high, low=low, close=close, volume=1.0
    )


def _signal(direction=SignalDirection.bullish, stop=95.0, target=110.0, symbol="AAPL") -> Signal:
    return Signal(
        symbol=symbol,
        direction=direction,
        price=100.0,
        score=85.0,
        stop_price=stop,
        target_price=target,
        indicators=IndicatorSnapshot(sma_fast=1, sma_slow=1, rsi14=50, volume_ratio=2),
        triggered_rules=["x"],
        sources=[SignalSource.watchlist],
        generated_at=DAY0,
    )


def _suggestion(**kwargs) -> Suggestion:
    signal = _signal(**kwargs)
    return Suggestion(
        id=1,
        **signal.model_dump(exclude={"generated_at"}),
        status=SuggestionStatus.pending,
        generated_at=signal.generated_at,
        updated_at=signal.generated_at,
    )


NOW = DAY0 + timedelta(days=3)


def test_bullish_target_hit():
    outcome, price, _, _ = evaluate(_suggestion(), [_bar(1, 99, 103), _bar(2, 100, 111)], NOW)
    assert (outcome, price) == (SuggestionOutcome.target_hit, 110.0)


def test_bullish_stopped():
    outcome, price, _, _ = evaluate(_suggestion(), [_bar(1, 94, 101)], NOW)
    assert (outcome, price) == (SuggestionOutcome.stopped, 95.0)


def test_bearish_target_and_stop_are_mirrored():
    bearish = {"direction": SignalDirection.bearish, "stop": 105.0, "target": 90.0}
    assert evaluate(_suggestion(**bearish), [_bar(1, 89, 101)], NOW)[0] == SuggestionOutcome.target_hit
    assert evaluate(_suggestion(**bearish), [_bar(1, 99, 106)], NOW)[0] == SuggestionOutcome.stopped


def test_bar_touching_both_levels_resolves_as_stopped():
    assert evaluate(_suggestion(), [_bar(1, 94, 111)], NOW)[0] == SuggestionOutcome.stopped


def test_signal_day_bar_is_ignored():
    assert evaluate(_suggestion(), [_bar(0, 90, 120)], NOW)[0] == SuggestionOutcome.open


def test_stays_open_and_reports_last_price():
    outcome, price, at, last = evaluate(_suggestion(), [_bar(1, 98, 102, close=101.0)], NOW)
    assert (outcome, price, at, last) == (SuggestionOutcome.open, None, None, 101.0)


def test_expires_after_max_age_at_last_close():
    later = DAY0 + timedelta(days=11)
    outcome, price, _, _ = evaluate(_suggestion(), [_bar(1, 98, 102, close=101.0)], later)
    assert (outcome, price) == (SuggestionOutcome.expired, 101.0)


def test_atr_and_trade_plan_on_crossover_signal():
    bars = crossover_bars("bullish")
    assert atr(bars) is not None
    signal = detect_crossover_signal(ScanCandidate("AAPL", {SignalSource.watchlist}), bars)
    assert signal.stop_price < signal.price < signal.target_price
    candidate = ScanCandidate("AAPL", {SignalSource.watchlist})
    bearish = detect_crossover_signal(candidate, crossover_bars("bearish"))
    assert bearish.target_price < bearish.price < bearish.stop_price


def test_monitor_run_once_resolves_and_performance_summarizes(tmp_path):
    store = SuggestionStore(tmp_path / "s.db")
    win = store.create(_signal(symbol="AAA"), None)
    loss = store.create(_signal(symbol="BBB"), None)
    pending = store.create(_signal(symbol="CCC"), None)

    bars = {
        "AAA": [_bar(1, 99, 112)],
        "BBB": [_bar(1, 90, 101)],
        "CCC": [_bar(1, 99, 102, close=101.0)],
    }
    client = SimpleNamespace(get_bars_multi=lambda symbols, start=None: bars)
    connection = FakeAlpacaConnection(SimpleNamespace(market_data_client=client))
    monitor = SuggestionMonitor(connection, store, max_age_days=10_000)

    assert monitor.run_once() == 2

    by_id = {s.id: s for s in store.list_all()}
    assert by_id[win.id].outcome == SuggestionOutcome.target_hit
    assert by_id[win.id].return_pct == 10.0
    assert by_id[loss.id].outcome == SuggestionOutcome.stopped
    assert by_id[loss.id].return_pct == -5.0
    assert by_id[pending.id].outcome == SuggestionOutcome.open
    assert by_id[pending.id].return_pct == 1.0

    summary = store.performance()
    assert (summary.total, summary.open, summary.target_hit, summary.stopped) == (3, 1, 1, 1)
    assert summary.win_rate_pct == 50.0
    assert summary.avg_return_pct == 2.5
    # Resolved rows are no longer re-evaluated.
    assert [s.id for s in store.list_open()] == [pending.id]


def test_monitor_skips_without_connection(tmp_path):
    store = SuggestionStore(tmp_path / "s.db")
    store.create(_signal(), None)
    assert SuggestionMonitor(FakeAlpacaConnection(None), store).run_once() == 0


def test_existing_database_is_migrated(tmp_path):
    db = tmp_path / "old.db"
    SuggestionStore(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE suggestions")
        conn.execute(
            "CREATE TABLE suggestions (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, "
            "direction TEXT NOT NULL, price REAL NOT NULL, score REAL NOT NULL, "
            "indicators_json TEXT NOT NULL, triggered_rules_json TEXT NOT NULL, "
            "sources_json TEXT NOT NULL, rationale TEXT, status TEXT NOT NULL, "
            "generated_at TEXT NOT NULL, updated_at TEXT NOT NULL, dedupe_key TEXT NOT NULL)"
        )
    store = SuggestionStore(db)
    created = store.create(_signal(), None)
    assert created.outcome == SuggestionOutcome.open
    assert created.stop_price == 95.0


def test_performance_endpoint(suggestions_api_client):
    client, store = suggestions_api_client
    store.create(_signal(), None)
    response = client.get("/api/v1/suggestions/performance")
    assert response.status_code == 200
    assert response.json()["total"] == 1


def _ohlc(day: int, open_: float, high: float, low: float, close: float) -> HistoricalBar:
    return HistoricalBar(
        timestamp=DAY0 + timedelta(days=day), open=open_, high=high, low=low, close=close, volume=1.0
    )


def test_gap_through_the_stop_fills_at_the_open_not_the_stop():
    gap = _ohlc(1, open_=90.0, high=91.0, low=89.0, close=90.0)
    outcome, price, _, _ = evaluate(_suggestion(), [gap], NOW)
    assert (outcome, price) == (SuggestionOutcome.stopped, 90.0)

    bearish = _suggestion(direction=SignalDirection.bearish, stop=105.0, target=90.0)
    gap_up = _ohlc(1, open_=110.0, high=112.0, low=109.0, close=111.0)
    assert evaluate(bearish, [gap_up], NOW)[:2] == (SuggestionOutcome.stopped, 110.0)


def test_first_session_after_an_evening_signal_is_checked():
    # Signal generated after 8pm ET on Sep 1 has a UTC date of Sep 2, but it fired on the
    # Sep 1 bar - the Sep 2 session is the first one that must be replayed.
    suggestion = _suggestion()
    suggestion.generated_at = datetime(2026, 9, 2, 1, 30, tzinfo=UTC)
    suggestion.bar_date = date(2026, 9, 1)
    later = suggestion.generated_at + timedelta(days=1)
    outcome, price, _, _ = evaluate(suggestion, [_bar(1, 94, 101)], later)
    assert (outcome, price) == (SuggestionOutcome.stopped, 95.0)
