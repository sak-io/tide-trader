import asyncio
from types import SimpleNamespace

import pytest

from app.adapters.alpaca_market import AlpacaMarketDataClient
from app.engine.rationale import RationaleGenerator
from app.engine.scan_loop import ScanLoopConfig, SuggestionScanLoop
from app.engine.suggestion_store import SuggestionStore
from app.engine.watchlist_store import WatchlistStore
from tests.fakes import (
    FakeAlpacaConnection,
    FakeAnthropicClient,
    FakeBarsClient,
    FakeScreenerClient,
    crossover_bars,
)


@pytest.fixture
def watchlist_store(tmp_path) -> WatchlistStore:
    return WatchlistStore(tmp_path / "watchlist.db")


@pytest.fixture
def suggestion_store(tmp_path) -> SuggestionStore:
    return SuggestionStore(tmp_path / "suggestions.db")


def _market_client(
    most_active_symbols: list[str],
    gainer_symbols: list[str],
    loser_symbols: list[str],
    bars_by_symbol: dict[str, list],
) -> AlpacaMarketDataClient:
    screener = FakeScreenerClient(
        most_actives=SimpleNamespace(
            most_actives=[SimpleNamespace(symbol=s, volume=1.0, trade_count=1.0) for s in most_active_symbols]
        ),
        movers=SimpleNamespace(
            gainers=[
                SimpleNamespace(symbol=s, percent_change=1.0, change=1.0, price=1.0) for s in gainer_symbols
            ],
            losers=[
                SimpleNamespace(symbol=s, percent_change=-1.0, change=-1.0, price=1.0)
                for s in loser_symbols
            ],
        ),
    )
    return AlpacaMarketDataClient(screener, FakeBarsClient(bars_by_symbol))


def _loop(
    watchlist_store: WatchlistStore,
    suggestion_store: SuggestionStore,
    connection: FakeAlpacaConnection,
    rationale_client=None,
    config: ScanLoopConfig | None = None,
) -> SuggestionScanLoop:
    return SuggestionScanLoop(
        connection=connection,
        watchlist_store=watchlist_store,
        suggestion_store=suggestion_store,
        rationale_generator=RationaleGenerator(client=rationale_client, model="claude-opus-5"),
        config=config,
    )


async def test_run_once_skips_when_not_connected(watchlist_store, suggestion_store):
    loop = _loop(watchlist_store, suggestion_store, FakeAlpacaConnection(session=None))

    await loop.run_once()

    assert suggestion_store.list_all() == []


async def test_run_once_creates_a_suggestion_for_a_qualifying_watchlist_signal(
    watchlist_store, suggestion_store
):
    watchlist_store.add("AAPL")
    market_client = _market_client([], [], [], {"AAPL": crossover_bars(direction="bullish")})
    connection = FakeAlpacaConnection(session=SimpleNamespace(market_data_client=market_client))
    rationale_client = FakeAnthropicClient(response_text="Strong momentum.")

    await _loop(watchlist_store, suggestion_store, connection, rationale_client).run_once()

    suggestions = suggestion_store.list_all()
    assert len(suggestions) == 1
    assert suggestions[0].symbol == "AAPL"
    assert suggestions[0].rationale == "Strong momentum."
    assert set(suggestions[0].sources) == {"watchlist"}


async def test_run_once_keeps_both_source_tags_for_dual_membership(watchlist_store, suggestion_store):
    watchlist_store.add("AAPL")
    market_client = _market_client([], ["AAPL"], [], {"AAPL": crossover_bars(direction="bullish")})
    connection = FakeAlpacaConnection(session=SimpleNamespace(market_data_client=market_client))

    await _loop(watchlist_store, suggestion_store, connection).run_once()

    suggestions = suggestion_store.list_all()
    assert len(suggestions) == 1
    assert {s.value for s in suggestions[0].sources} == {"watchlist", "alpaca"}
    assert suggestions[0].rationale is None  # no rationale client configured - failure tolerant


async def test_run_once_skips_a_duplicate_signal_already_recorded_today(watchlist_store, suggestion_store):
    watchlist_store.add("AAPL")
    market_client = _market_client([], [], [], {"AAPL": crossover_bars(direction="bullish")})
    connection = FakeAlpacaConnection(session=SimpleNamespace(market_data_client=market_client))
    loop = _loop(watchlist_store, suggestion_store, connection)

    await loop.run_once()
    await loop.run_once()

    assert len(suggestion_store.list_all()) == 1


async def test_run_once_tolerates_a_rationale_failure(watchlist_store, suggestion_store):
    watchlist_store.add("AAPL")
    market_client = _market_client([], [], [], {"AAPL": crossover_bars(direction="bullish")})
    connection = FakeAlpacaConnection(session=SimpleNamespace(market_data_client=market_client))
    failing_client = FakeAnthropicClient(should_raise=True)

    await _loop(watchlist_store, suggestion_store, connection, failing_client).run_once()

    suggestions = suggestion_store.list_all()
    assert len(suggestions) == 1
    assert suggestions[0].rationale is None


async def test_run_once_does_nothing_with_an_empty_universe(watchlist_store, suggestion_store):
    market_client = _market_client([], [], [], {})
    connection = FakeAlpacaConnection(session=SimpleNamespace(market_data_client=market_client))

    await _loop(watchlist_store, suggestion_store, connection).run_once()

    assert suggestion_store.list_all() == []


async def test_run_once_respects_the_configured_min_score(watchlist_store, suggestion_store):
    watchlist_store.add("AAPL")
    market_client = _market_client([], [], [], {"AAPL": crossover_bars(direction="bullish")})
    connection = FakeAlpacaConnection(session=SimpleNamespace(market_data_client=market_client))

    await _loop(
        watchlist_store, suggestion_store, connection, config=ScanLoopConfig(min_score=90)
    ).run_once()

    assert suggestion_store.list_all() == []


async def test_run_forever_survives_a_bad_cycle_and_is_cancellable(watchlist_store, suggestion_store):
    connection = FakeAlpacaConnection(session=None)
    loop = _loop(
        watchlist_store, suggestion_store, connection, config=ScanLoopConfig(interval_seconds=0)
    )

    task = asyncio.create_task(loop.run_forever())
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_run_forever_logs_and_continues_after_run_once_raises(
    watchlist_store, suggestion_store, monkeypatch
):
    connection = FakeAlpacaConnection(session=None)
    loop = _loop(
        watchlist_store, suggestion_store, connection, config=ScanLoopConfig(interval_seconds=0)
    )

    call_count = 0
    original_run_once = loop.run_once

    async def flaky_run_once():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")
        await original_run_once()

    monkeypatch.setattr(loop, "run_once", flaky_run_once)

    task = asyncio.create_task(loop.run_forever())
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert call_count >= 2


async def test_run_once_does_not_re_log_the_same_bar_after_the_utc_date_rolls_over(
    watchlist_store, suggestion_store, monkeypatch
):
    from datetime import UTC, datetime

    import app.engine.screener as screener_module

    watchlist_store.add("AAPL")
    market_client = _market_client([], [], [], {"AAPL": crossover_bars(direction="bullish")})
    connection = FakeAlpacaConnection(session=SimpleNamespace(market_data_client=market_client))
    loop = _loop(watchlist_store, suggestion_store, connection)

    await loop.run_once()

    class _Tomorrow(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2099, 1, 1, tzinfo=UTC)

    monkeypatch.setattr(screener_module, "datetime", _Tomorrow)
    await loop.run_once()  # same Friday bar, later wall-clock date

    assert len(suggestion_store.list_all()) == 1


async def test_run_once_runs_blocking_work_off_the_event_loop(watchlist_store, suggestion_store):
    import threading

    watchlist_store.add("AAPL")
    market_client = _market_client([], [], [], {"AAPL": crossover_bars(direction="bullish")})
    threads = []
    original = market_client.get_most_active

    def recording_get_most_active(top=10):
        threads.append(threading.current_thread())
        return original(top)

    market_client.get_most_active = recording_get_most_active
    connection = FakeAlpacaConnection(session=SimpleNamespace(market_data_client=market_client))

    await _loop(watchlist_store, suggestion_store, connection).run_once()

    assert threads and threads[0] is not threading.main_thread()


async def test_a_monitor_failure_does_not_stop_the_scan(watchlist_store, suggestion_store, monkeypatch):
    watchlist_store.add("AAPL")
    market_client = _market_client([], [], [], {"AAPL": crossover_bars(direction="bullish")})
    connection = FakeAlpacaConnection(session=SimpleNamespace(market_data_client=market_client))
    loop = _loop(watchlist_store, suggestion_store, connection)

    def boom():
        raise RuntimeError("monitor down")

    monkeypatch.setattr(loop._monitor, "run_once", boom)
    await loop.run_once()

    assert len(suggestion_store.list_all()) == 1


async def test_losing_a_race_to_another_writer_is_not_an_error(watchlist_store, suggestion_store, monkeypatch):
    watchlist_store.add("AAPL")
    market_client = _market_client([], [], [], {"AAPL": crossover_bars(direction="bullish")})
    connection = FakeAlpacaConnection(session=SimpleNamespace(market_data_client=market_client))
    loop = _loop(watchlist_store, suggestion_store, connection)

    # The row appears between the existence check and the insert.
    signals = loop._find_signals()
    suggestion_store.create(signals[0], None)
    monkeypatch.setattr(loop, "_find_signals", lambda: signals)

    await loop.run_once()

    assert len(suggestion_store.list_all()) == 1
