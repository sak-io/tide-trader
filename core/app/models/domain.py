from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class OrderSide(str, Enum):
    buy = "buy"
    sell = "sell"


class OrderType(str, Enum):
    market = "market"
    limit = "limit"


class OrderStatus(str, Enum):
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


class KillSwitchAction(str, Enum):
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
