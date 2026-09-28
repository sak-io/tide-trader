from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from alpaca.data.enums import DataFeed
from alpaca.data.historical.screener import ScreenerClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import MarketMoversRequest, MostActivesRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from app.models.domain import ActiveTicker, HistoricalBar, MarketMovers, MoverTicker

_TIMEFRAME_PRESETS: dict[str, TimeFrame] = {
    "1Min": TimeFrame(1, TimeFrameUnit.Minute),
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
    "1Day": TimeFrame(1, TimeFrameUnit.Day),
}


def parse_timeframe(value: str) -> TimeFrame:
    try:
        return _TIMEFRAME_PRESETS[value]
    except KeyError:
        supported = ", ".join(_TIMEFRAME_PRESETS)
        raise ValueError(f"Unsupported timeframe '{value}'. Supported: {supported}") from None


class ScreenerClientProtocol(Protocol):
    """The subset of alpaca-py's ScreenerClient this adapter depends on."""

    def get_most_actives(self, request_params: Any) -> Any: ...
    def get_market_movers(self, request_params: Any) -> Any: ...


class StockBarsClientProtocol(Protocol):
    """The subset of alpaca-py's StockHistoricalDataClient this adapter depends on."""

    def get_stock_bars(self, request_params: Any) -> Any: ...


class AlpacaMarketDataClient:
    """Read-only market research data: most-active tickers, movers, historical bars."""

    def __init__(self, screener_client: ScreenerClientProtocol, bars_client: StockBarsClientProtocol):
        self._screener = screener_client
        self._bars = bars_client

    @classmethod
    def from_credentials(cls, api_key_id: str, secret_key: str) -> "AlpacaMarketDataClient":
        screener = ScreenerClient(
            api_key=api_key_id,
            secret_key=secret_key,
        )
        bars = StockHistoricalDataClient(
            api_key=api_key_id,
            secret_key=secret_key,
        )
        return cls(screener, bars)

    def get_most_active(self, top: int = 10) -> list[ActiveTicker]:
        result = self._screener.get_most_actives(MostActivesRequest(top=top))
        return [
            ActiveTicker(symbol=item.symbol, volume=item.volume, trade_count=item.trade_count)
            for item in result.most_actives
        ]

    def get_movers(self, top: int = 10) -> MarketMovers:
        result = self._screener.get_market_movers(MarketMoversRequest(top=top))
        return MarketMovers(
            gainers=[self._to_mover(item) for item in result.gainers],
            losers=[self._to_mover(item) for item in result.losers],
        )

    def get_bars(
        self,
        symbol: str,
        timeframe: str = "1Day",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[HistoricalBar]:
        symbol = symbol.strip().upper()
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=parse_timeframe(timeframe),
            start=start or (datetime.now(UTC) - timedelta(days=30)),
            end=end or datetime.now(UTC),
            limit=limit,
            # The paper account's market data subscription only entitles IEX,
            # not the full SIP feed (Alpaca's default) - matches the streaming feed.
            feed=DataFeed.IEX,
        )
        bar_set = self._bars.get_stock_bars(request)

        return [
            HistoricalBar(
                timestamp=bar.timestamp,
                open=float(bar.open),
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
                volume=float(bar.volume),
            )
            for bar in bar_set.data.get(symbol, [])
        ]

    @staticmethod
    def _to_mover(item: Any) -> MoverTicker:
        return MoverTicker(
            symbol=item.symbol,
            percent_change=item.percent_change,
            change=item.change,
            price=item.price,
        )
