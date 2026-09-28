import asyncio
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.adapters.alpaca_data import (
    AlpacaStreamRunner,
    MarketDataHub,
    bar_to_message,
    build_stream_runner,
    quote_to_message,
    trade_to_message,
)
from app.config import Settings
from tests.fakes import FakeStreamClient


async def test_publish_delivers_only_to_subscribed_queue():
    hub = MarketDataHub()
    queue_a: asyncio.Queue = asyncio.Queue()
    queue_b: asyncio.Queue = asyncio.Queue()

    await hub.subscribe(queue_a, ["AAPL"])
    await hub.subscribe(queue_b, ["MSFT"])

    await hub.publish("AAPL", {"type": "trade", "symbol": "AAPL"})

    assert queue_a.get_nowait() == {"type": "trade", "symbol": "AAPL"}
    assert queue_b.empty()


async def test_symbol_hooks_fire_only_on_first_subscribe_and_last_unsubscribe():
    hub = MarketDataHub()
    added: list[str] = []
    removed: list[str] = []
    hub.set_symbol_hooks(added.append, removed.append)

    queue_a: asyncio.Queue = asyncio.Queue()
    queue_b: asyncio.Queue = asyncio.Queue()

    await hub.subscribe(queue_a, ["AAPL"])
    await hub.subscribe(queue_b, ["AAPL"])  # second subscriber - must not re-fire
    assert added == ["AAPL"]

    await hub.unsubscribe(queue_a, ["AAPL"])
    assert removed == []  # queue_b still watching AAPL

    await hub.unsubscribe(queue_b, ["AAPL"])
    assert removed == ["AAPL"]


async def test_unsubscribe_all_removes_from_every_symbol():
    hub = MarketDataHub()
    queue: asyncio.Queue = asyncio.Queue()

    await hub.subscribe(queue, ["AAPL", "MSFT"])
    await hub.unsubscribe(queue, None)

    assert hub.subscribed_symbols() == []


async def test_publish_threadsafe_delivers_from_a_different_thread():
    loop = asyncio.get_running_loop()
    hub = MarketDataHub(loop=loop)
    queue: asyncio.Queue = asyncio.Queue()
    await hub.subscribe(queue, ["AAPL"])

    thread = threading.Thread(
        target=lambda: hub.publish_threadsafe("AAPL", {"type": "trade", "symbol": "AAPL", "price": 1.0})
    )
    thread.start()
    thread.join()

    message = await asyncio.wait_for(queue.get(), timeout=1)
    assert message["symbol"] == "AAPL"


async def test_publish_threadsafe_is_a_noop_without_a_bound_loop():
    hub = MarketDataHub()  # no loop bound
    hub.publish_threadsafe("AAPL", {"type": "trade"})  # must not raise


def test_trade_to_message_conversion():
    trade = SimpleNamespace(symbol="AAPL", price=190.5, size=100, timestamp=datetime.now(timezone.utc))
    message = trade_to_message(trade)

    assert message == {
        "type": "trade",
        "symbol": "AAPL",
        "price": 190.5,
        "size": 100,
        "timestamp": trade.timestamp.isoformat(),
    }


def test_quote_to_message_conversion():
    quote = SimpleNamespace(
        symbol="AAPL",
        bid_price=190.0,
        bid_size=1,
        ask_price=190.5,
        ask_size=2,
        timestamp=datetime.now(timezone.utc),
    )
    message = quote_to_message(quote)

    assert message["type"] == "quote"
    assert message["bid_price"] == 190.0
    assert message["ask_size"] == 2


def test_bar_to_message_conversion():
    bar = SimpleNamespace(
        symbol="AAPL", open=190.0, high=191.0, low=189.5, close=190.8, volume=12345,
        timestamp=datetime.now(timezone.utc),
    )
    message = bar_to_message(bar)

    assert message["type"] == "bar"
    assert message["close"] == 190.8
    assert message["volume"] == 12345


async def test_stream_runner_subscribes_upstream_on_first_subscriber():
    loop = asyncio.get_running_loop()
    hub = MarketDataHub(loop=loop)
    fake_client = FakeStreamClient()
    AlpacaStreamRunner(fake_client, hub)  # wires itself into the hub's hooks

    queue: asyncio.Queue = asyncio.Queue()
    await hub.subscribe(queue, ["AAPL"])

    assert "AAPL" in fake_client.trade_handlers
    assert "AAPL" in fake_client.quote_handlers
    assert "AAPL" in fake_client.bar_handlers


async def test_stream_runner_unsubscribes_upstream_when_last_client_leaves():
    loop = asyncio.get_running_loop()
    hub = MarketDataHub(loop=loop)
    fake_client = FakeStreamClient()
    AlpacaStreamRunner(fake_client, hub)

    queue: asyncio.Queue = asyncio.Queue()
    await hub.subscribe(queue, ["AAPL"])
    await hub.unsubscribe(queue, ["AAPL"])

    assert "AAPL" in fake_client.unsubscribed_trades
    assert "AAPL" in fake_client.unsubscribed_quotes
    assert "AAPL" in fake_client.unsubscribed_bars


async def test_stream_runner_handler_publishes_trade_into_hub():
    loop = asyncio.get_running_loop()
    hub = MarketDataHub(loop=loop)
    fake_client = FakeStreamClient()
    runner = AlpacaStreamRunner(fake_client, hub)

    queue: asyncio.Queue = asyncio.Queue()
    await hub.subscribe(queue, ["AAPL"])

    trade = SimpleNamespace(symbol="AAPL", price=100.0, size=1, timestamp=datetime.now(timezone.utc))
    await runner._handle_trade(trade)

    message = await asyncio.wait_for(queue.get(), timeout=1)
    assert message["type"] == "trade"
    assert message["price"] == 100.0


async def test_stream_runner_handler_publishes_quote_into_hub():
    loop = asyncio.get_running_loop()
    hub = MarketDataHub(loop=loop)
    fake_client = FakeStreamClient()
    runner = AlpacaStreamRunner(fake_client, hub)

    queue: asyncio.Queue = asyncio.Queue()
    await hub.subscribe(queue, ["AAPL"])

    quote = SimpleNamespace(
        symbol="AAPL", bid_price=99.0, bid_size=1, ask_price=100.0, ask_size=2,
        timestamp=datetime.now(timezone.utc),
    )
    await runner._handle_quote(quote)

    message = await asyncio.wait_for(queue.get(), timeout=1)
    assert message["type"] == "quote"
    assert message["ask_price"] == 100.0


async def test_stream_runner_handler_publishes_bar_into_hub():
    loop = asyncio.get_running_loop()
    hub = MarketDataHub(loop=loop)
    fake_client = FakeStreamClient()
    runner = AlpacaStreamRunner(fake_client, hub)

    queue: asyncio.Queue = asyncio.Queue()
    await hub.subscribe(queue, ["AAPL"])

    bar = SimpleNamespace(
        symbol="AAPL", open=100.0, high=101.0, low=99.5, close=100.5, volume=500,
        timestamp=datetime.now(timezone.utc),
    )
    await runner._handle_bar(bar)

    message = await asyncio.wait_for(queue.get(), timeout=1)
    assert message["type"] == "bar"
    assert message["close"] == 100.5


def test_stream_runner_start_and_stop_manage_background_thread():
    hub = MarketDataHub()
    fake_client = FakeStreamClient()
    runner = AlpacaStreamRunner(fake_client, hub)

    runner.start()
    runner.stop()

    assert fake_client.stopped is True


def test_build_stream_runner_always_returns_none():
    """Live streaming credentials now come from the in-memory AlpacaConnection,
    populated after startup via POST /api/v1/alpaca/connect - Settings no longer
    carries any Alpaca credential to build a stream client from at lifespan
    startup, so this is always None (see build_stream_runner's docstring)."""
    settings = Settings()
    hub = MarketDataHub()

    assert build_stream_runner(settings, hub) is None
