from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any


class FakeTradingClient:
    """Stands in for alpaca-py's TradingClient in tests - no network, no real credentials."""

    def __init__(self, equity: float = 10000.0, last_equity: float = 10100.0):
        self.account = SimpleNamespace(
            equity=str(equity),
            last_equity=str(last_equity),
            cash="5000.00",
            buying_power="20000.00",
            portfolio_value=str(equity),
        )
        self.positions: list[Any] = []
        self.orders: dict[str, SimpleNamespace] = {}
        self.canceled: list[str] = []
        self._next_id = 1

    def get_account(self) -> SimpleNamespace:
        return self.account

    def get_all_positions(self) -> list[Any]:
        return self.positions

    def submit_order(self, order_data: Any) -> SimpleNamespace:
        order_id = f"order-{self._next_id}"
        self._next_id += 1
        order = SimpleNamespace(
            id=order_id,
            symbol=order_data.symbol,
            qty=order_data.qty,
            side=order_data.side,
            status=SimpleNamespace(value="accepted"),
            submitted_at=datetime.now(UTC),
            filled_qty="0",
            filled_avg_price=None,
            limit_price=getattr(order_data, "limit_price", None),
        )
        self.orders[order_id] = order
        return order

    def cancel_order_by_id(self, order_id: str) -> None:
        self.canceled.append(order_id)

    def get_order_by_id(self, order_id: str, filter: Any = None) -> SimpleNamespace:
        return self.orders[order_id]


class FakeMarketDataClient:
    """Stands in for alpaca-py's StockHistoricalDataClient in tests."""

    def __init__(self, prices: dict[str, float]):
        self.prices = prices

    def get_stock_latest_trade(self, request_params: Any) -> dict[str, SimpleNamespace]:
        symbol = request_params.symbol_or_symbols
        return {symbol: SimpleNamespace(price=self.prices[symbol])}


class FakeScreenerClient:
    """Stands in for alpaca-py's ScreenerClient in tests."""

    def __init__(self, most_actives: Any = None, movers: Any = None):
        self._most_actives = most_actives
        self._movers = movers

    def get_most_actives(self, request_params: Any) -> Any:
        return self._most_actives

    def get_market_movers(self, request_params: Any) -> Any:
        return self._movers


class FakeBarsClient:
    """Stands in for alpaca-py's StockHistoricalDataClient (bars only) in tests."""

    def __init__(self, bars_by_symbol: dict[str, list[Any]]):
        self.bars_by_symbol = bars_by_symbol
        self.last_request: Any = None

    def get_stock_bars(self, request_params: Any) -> SimpleNamespace:
        self.last_request = request_params
        return SimpleNamespace(data=self.bars_by_symbol)


class FakeStreamClient:
    """Stands in for alpaca-py's StockDataStream in tests - no real WebSocket connection."""

    def __init__(self):
        self.trade_handlers: dict[str, Any] = {}
        self.quote_handlers: dict[str, Any] = {}
        self.bar_handlers: dict[str, Any] = {}
        self.unsubscribed_trades: list[str] = []
        self.unsubscribed_quotes: list[str] = []
        self.unsubscribed_bars: list[str] = []
        self.ran = False
        self.stopped = False

    def subscribe_trades(self, handler: Any, *symbols: str) -> None:
        for symbol in symbols:
            self.trade_handlers[symbol] = handler

    def subscribe_quotes(self, handler: Any, *symbols: str) -> None:
        for symbol in symbols:
            self.quote_handlers[symbol] = handler

    def subscribe_bars(self, handler: Any, *symbols: str) -> None:
        for symbol in symbols:
            self.bar_handlers[symbol] = handler

    def unsubscribe_trades(self, *symbols: str) -> None:
        self.unsubscribed_trades.extend(symbols)

    def unsubscribe_quotes(self, *symbols: str) -> None:
        self.unsubscribed_quotes.extend(symbols)

    def unsubscribe_bars(self, *symbols: str) -> None:
        self.unsubscribed_bars.extend(symbols)

    def run(self) -> None:
        self.ran = True

    def stop(self) -> None:
        self.stopped = True
