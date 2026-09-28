from datetime import UTC, datetime
from typing import Any, Protocol

from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from alpaca.trading.enums import TimeInForce
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

from app.models.domain import (
    AccountSummary,
    OrderRequest,
    OrderResponse,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)

_STATUS_MAP = {
    "new": OrderStatus.new,
    "pending_new": OrderStatus.pending_new,
    "accepted": OrderStatus.accepted,
    "partially_filled": OrderStatus.partially_filled,
    "filled": OrderStatus.filled,
    "canceled": OrderStatus.canceled,
    "expired": OrderStatus.expired,
    "rejected": OrderStatus.rejected,
}


class TradingClientProtocol(Protocol):
    """The subset of alpaca-py's TradingClient this adapter depends on.

    Defined so tests can substitute a fake implementation without touching
    the network or requiring real credentials.
    """

    def get_account(self) -> Any: ...
    def get_all_positions(self) -> Any: ...
    def submit_order(self, order_data: Any) -> Any: ...
    def cancel_order_by_id(self, order_id: str) -> Any: ...
    def get_order_by_id(self, order_id: str) -> Any: ...


class LatestTradeClientProtocol(Protocol):
    """The subset of alpaca-py's StockHistoricalDataClient this adapter depends on."""

    def get_stock_latest_trade(self, request_params: Any) -> Any: ...


class AlpacaTradeAdapter:
    """Thin wrapper around alpaca-py, translating to/from our own domain models."""

    def __init__(self, client: TradingClientProtocol, market_data_client: LatestTradeClientProtocol):
        self._client = client
        self._market_data_client = market_data_client

    @classmethod
    def from_credentials(cls, api_key_id: str, secret_key: str, paper: bool) -> "AlpacaTradeAdapter":
        client = TradingClient(
            api_key=api_key_id,
            secret_key=secret_key,
            paper=paper,
        )
        market_data_client = StockHistoricalDataClient(
            api_key=api_key_id,
            secret_key=secret_key,
        )
        return cls(client, market_data_client)

    def get_latest_price(self, symbol: str) -> float:
        request = StockLatestTradeRequest(symbol_or_symbols=symbol)
        trades = self._market_data_client.get_stock_latest_trade(request)
        return float(trades[symbol].price)

    def get_account(self) -> AccountSummary:
        account = self._client.get_account()
        equity = float(account.equity)
        last_equity = float(account.last_equity)
        daily_pl = equity - last_equity
        daily_pl_pct = (daily_pl / last_equity) if last_equity else 0.0
        return AccountSummary(
            equity=equity,
            cash=float(account.cash),
            buying_power=float(account.buying_power),
            portfolio_value=float(account.portfolio_value),
            daily_pl=daily_pl,
            daily_pl_pct=daily_pl_pct,
        )

    def get_positions(self) -> list[Position]:
        positions = self._client.get_all_positions()
        return [
            Position(
                symbol=p.symbol,
                qty=float(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                market_value=float(p.market_value),
                current_price=float(p.current_price),
                unrealized_pl=float(p.unrealized_pl),
                unrealized_plpc=float(p.unrealized_plpc),
            )
            for p in positions
        ]

    def submit_order(self, order: OrderRequest) -> OrderResponse:
        side = AlpacaOrderSide.BUY if order.side == OrderSide.buy else AlpacaOrderSide.SELL

        request: MarketOrderRequest | LimitOrderRequest
        if order.order_type == OrderType.limit:
            request = LimitOrderRequest(
                symbol=order.symbol,
                qty=order.qty,
                side=side,
                time_in_force=TimeInForce.DAY,
                limit_price=order.limit_price,
            )
        else:
            request = MarketOrderRequest(
                symbol=order.symbol,
                qty=order.qty,
                side=side,
                time_in_force=TimeInForce.DAY,
            )

        raw = self._client.submit_order(request)
        return self._to_order_response(raw)

    def cancel_order(self, order_id: str) -> None:
        self._client.cancel_order_by_id(order_id)

    def get_order(self, order_id: str) -> OrderResponse:
        raw = self._client.get_order_by_id(order_id)
        return self._to_order_response(raw)

    @staticmethod
    def _to_order_response(raw: Any) -> OrderResponse:
        raw_status = raw.status.value if hasattr(raw.status, "value") else str(raw.status)
        status = _STATUS_MAP.get(raw_status, OrderStatus.other)

        raw_side = raw.side.value if hasattr(raw.side, "value") else str(raw.side)
        side = OrderSide.buy if raw_side == "buy" else OrderSide.sell

        limit_price = raw.limit_price
        order_type = OrderType.limit if limit_price is not None else OrderType.market

        filled_avg_price = raw.filled_avg_price
        submitted_at = raw.submitted_at or datetime.now(UTC)

        return OrderResponse(
            id=str(raw.id),
            symbol=raw.symbol,
            qty=float(raw.qty),
            side=side,
            order_type=order_type,
            status=status,
            submitted_at=submitted_at,
            filled_qty=float(raw.filled_qty or 0),
            filled_avg_price=float(filled_avg_price) if filled_avg_price is not None else None,
        )
