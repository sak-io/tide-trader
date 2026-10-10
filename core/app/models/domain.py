from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class OrderSide(StrEnum):
    buy = "buy"
    sell = "sell"


class OrderType(StrEnum):
    market = "market"
    limit = "limit"


class OrderStatus(StrEnum):
    new = "new"
    pending_new = "pending_new"
    accepted = "accepted"
    partially_filled = "partially_filled"
    filled = "filled"
    canceled = "canceled"
    expired = "expired"
    rejected = "rejected"
    other = "other"


class OrderRequest(BaseModel):
    symbol: str
    qty: float = Field(gt=0)
    side: OrderSide
    order_type: OrderType = OrderType.market
    limit_price: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def normalize(self) -> "OrderRequest":
        self.symbol = self.symbol.strip().upper()
        if self.order_type == OrderType.limit and self.limit_price is None:
            raise ValueError("limit_price is required for limit orders")
        return self


class OrderResponse(BaseModel):
    id: str
    symbol: str
    qty: float
    side: OrderSide
    order_type: OrderType
    status: OrderStatus
    submitted_at: datetime
    filled_qty: float = 0
    filled_avg_price: float | None = None


class Position(BaseModel):
    symbol: str
    qty: float
    avg_entry_price: float
    market_value: float
    current_price: float
    unrealized_pl: float
    unrealized_plpc: float


class AccountSummary(BaseModel):
    equity: float
    cash: float
    buying_power: float
    portfolio_value: float
    daily_pl: float
    daily_pl_pct: float


class KillSwitchAction(StrEnum):
    activate = "activate"
    reset = "reset"


class KillSwitchRequest(BaseModel):
    action: KillSwitchAction
    reason: str | None = None


class KillSwitchStatus(BaseModel):
    kill_switch_active: bool
    reason: str | None = None


class ActiveTicker(BaseModel):
    symbol: str
    volume: float
    trade_count: float


class MoverTicker(BaseModel):
    symbol: str
    percent_change: float
    change: float
    price: float


class MarketMovers(BaseModel):
    gainers: list[MoverTicker]
    losers: list[MoverTicker]


class HistoricalBar(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class AlpacaConnectRequest(BaseModel):
    api_key_id: str = Field(min_length=1)
    secret_key: str = Field(min_length=1)


class AlpacaStatus(BaseModel):
    connected: bool


class SignalSource(StrEnum):
    alpaca = "alpaca"
    watchlist = "watchlist"


class SignalDirection(StrEnum):
    bullish = "bullish"
    bearish = "bearish"


class IndicatorSnapshot(BaseModel):
    sma_fast: float
    sma_slow: float
    rsi14: float
    volume_ratio: float


class Signal(BaseModel):
    symbol: str
    direction: SignalDirection
    price: float
    score: float
    stop_price: float | None = None
    target_price: float | None = None
    bar_date: date | None = None  # date of the daily bar the signal fired on
    indicators: IndicatorSnapshot
    triggered_rules: list[str]
    sources: list[SignalSource]
    generated_at: datetime


class SuggestionStatus(StrEnum):
    pending = "pending"
    dismissed = "dismissed"


class SuggestionOutcome(StrEnum):
    open = "open"
    target_hit = "target_hit"
    stopped = "stopped"
    expired = "expired"


class Suggestion(BaseModel):
    id: int
    symbol: str
    direction: SignalDirection
    price: float
    score: float
    stop_price: float | None = None
    target_price: float | None = None
    bar_date: date | None = None
    outcome: SuggestionOutcome = SuggestionOutcome.open
    outcome_price: float | None = None
    outcome_at: datetime | None = None
    last_price: float | None = None
    return_pct: float | None = None
    indicators: IndicatorSnapshot
    triggered_rules: list[str]
    sources: list[SignalSource]
    rationale: str | None = None
    status: SuggestionStatus
    generated_at: datetime
    updated_at: datetime


class WatchlistItem(BaseModel):
    symbol: str
    added_at: datetime


class WatchlistAddRequest(BaseModel):
    symbol: str = Field(min_length=1)

    @model_validator(mode="after")
    def normalize(self) -> "WatchlistAddRequest":
        self.symbol = self.symbol.strip().upper()
        return self


class PerformanceSummary(BaseModel):
    """Hypothetical results of all suggestions - nothing here was ever traded."""

    total: int
    open: int
    target_hit: int
    stopped: int
    expired: int
    win_rate_pct: float | None
    avg_return_pct: float | None
