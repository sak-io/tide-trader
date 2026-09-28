import asyncio
import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any, Protocol

from app.config import Settings


def trade_to_message(trade: Any) -> dict:
    return {
        "type": "trade",
        "symbol": trade.symbol,
        "price": float(trade.price),
        "size": int(trade.size),
        "timestamp": trade.timestamp.isoformat(),
    }


def quote_to_message(quote: Any) -> dict:
    return {
        "type": "quote",
        "symbol": quote.symbol,
        "bid_price": float(quote.bid_price),
        "bid_size": int(quote.bid_size),
        "ask_price": float(quote.ask_price),
        "ask_size": int(quote.ask_size),
        "timestamp": quote.timestamp.isoformat(),
    }


def bar_to_message(bar: Any) -> dict:
    return {
        "type": "bar",
        "symbol": bar.symbol,
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
        "volume": int(bar.volume),
        "timestamp": bar.timestamp.isoformat(),
    }


class MarketDataHub:
    """Fans out realtime ticks to subscriber queues, one per connected WebSocket client.

    Invokes on_symbol_added/on_symbol_removed the moment a symbol's subscriber
    count goes from zero to one (or one to zero), so the caller can subscribe or
    unsubscribe the upstream Alpaca stream to match - Alpaca is only ever told
    about a symbol while at least one client actually wants it.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None):
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._loop = loop
        self._on_symbol_added: Callable[[str], None] | None = None
        self._on_symbol_removed: Callable[[str], None] | None = None

    def set_symbol_hooks(
        self,
        on_added: Callable[[str], None] | None,
        on_removed: Callable[[str], None] | None,
    ) -> None:
        self._on_symbol_added = on_added
        self._on_symbol_removed = on_removed

    async def subscribe(self, queue: asyncio.Queue, symbols: list[str]) -> None:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        newly_added: list[str] = []
        async with self._lock:
            for raw_symbol in symbols:
                symbol = raw_symbol.upper()
                subscribers = self._subscribers[symbol]
                if not subscribers:
                    newly_added.append(symbol)
                subscribers.add(queue)

        for symbol in newly_added:
            if self._on_symbol_added:
                self._on_symbol_added(symbol)

    async def unsubscribe(self, queue: asyncio.Queue, symbols: list[str] | None = None) -> None:
        removed: list[str] = []
        async with self._lock:
            targets = symbols if symbols is not None else list(self._subscribers.keys())
            for raw_symbol in targets:
                symbol = raw_symbol.upper()
                subscribers = self._subscribers.get(symbol)
                if subscribers and queue in subscribers:
                    subscribers.discard(queue)
                    if not subscribers:
                        removed.append(symbol)

        for symbol in removed:
            if self._on_symbol_removed:
                self._on_symbol_removed(symbol)

    def subscribed_symbols(self) -> list[str]:
        return [symbol for symbol, subs in self._subscribers.items() if subs]

    async def publish(self, symbol: str, message: dict) -> None:
        """Publish from within the hub's own event loop (e.g. in tests)."""
        async with self._lock:
            queues = list(self._subscribers.get(symbol.upper(), ()))
        for queue in queues:
            queue.put_nowait(message)

    def publish_threadsafe(self, symbol: str, message: dict) -> None:
        """Publish from a foreign thread/event loop (the Alpaca stream's own loop).

        The stream client runs its own asyncio loop in a background thread, so its
        handlers cannot touch this hub's queues directly - asyncio.Queue is bound
        to the loop that created it. call_soon_threadsafe hands the write back to
        this hub's own loop instead.
        """
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._publish_sync, symbol.upper(), message)

    def _publish_sync(self, symbol: str, message: dict) -> None:
        for queue in self._subscribers.get(symbol, ()):
            queue.put_nowait(message)


class StreamClientProtocol(Protocol):
    """The subset of alpaca-py's StockDataStream this runner depends on."""

    def subscribe_trades(self, handler: Callable[[Any], Any], *symbols: str) -> None: ...
    def subscribe_quotes(self, handler: Callable[[Any], Any], *symbols: str) -> None: ...
    def subscribe_bars(self, handler: Callable[[Any], Any], *symbols: str) -> None: ...
    def unsubscribe_trades(self, *symbols: str) -> None: ...
    def unsubscribe_quotes(self, *symbols: str) -> None: ...
    def unsubscribe_bars(self, *symbols: str) -> None: ...
    def run(self) -> None: ...
    def stop(self) -> None: ...


class AlpacaStreamRunner:
    """Owns the live Alpaca WebSocket connection and republishes ticks into a MarketDataHub.

    alpaca-py's stream client blocks its own thread running its own asyncio loop
    (`.run()` calls `asyncio.run(...)` internally), so it's started in a daemon
    thread here rather than awaited directly inside FastAPI's event loop.
    """

    def __init__(self, stream_client: StreamClientProtocol, hub: MarketDataHub):
        self._client = stream_client
        self._hub = hub
        self._thread: threading.Thread | None = None
        hub.set_symbol_hooks(self.on_symbol_added, self.on_symbol_removed)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._client.run, daemon=True, name="alpaca-stream")
        self._thread.start()

    def stop(self) -> None:
        self._client.stop()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def on_symbol_added(self, symbol: str) -> None:
        self._client.subscribe_trades(self._handle_trade, symbol)
        self._client.subscribe_quotes(self._handle_quote, symbol)
        self._client.subscribe_bars(self._handle_bar, symbol)

    def on_symbol_removed(self, symbol: str) -> None:
        self._client.unsubscribe_trades(symbol)
        self._client.unsubscribe_quotes(symbol)
        self._client.unsubscribe_bars(symbol)

    async def _handle_trade(self, trade: Any) -> None:
        self._hub.publish_threadsafe(trade.symbol, trade_to_message(trade))

    async def _handle_quote(self, quote: Any) -> None:
        self._hub.publish_threadsafe(quote.symbol, quote_to_message(quote))

    async def _handle_bar(self, bar: Any) -> None:
        self._hub.publish_threadsafe(bar.symbol, bar_to_message(bar))


def build_stream_runner(settings: Settings, hub: MarketDataHub) -> AlpacaStreamRunner | None:
    """Live IEX stream wiring is currently disabled.

    Alpaca credentials now live only in the in-memory `AlpacaConnection` populated by
    `POST /api/v1/alpaca/connect` (see `app.security.alpaca_session`), which happens
    well after this lifespan startup runs - `Settings` no longer carries any
    credential to build a stream client from here. Wiring this hub to that connection
    is deferred: `/ws/live` is unused by the Electron app today (it streams directly
    from Alpaca instead - see docs/ARCHITECTURE.md), so there's no active consumer to
    justify the added complexity yet. Kept as a function (rather than inlined `None`
    in `main.py`) so that future wiring, and the existing lifespan tests that
    monkeypatch it, don't need to change shape.
    """
    del settings, hub
    return None
