"""Background loop: build a scan universe, score crossovers, persist suggestions.

Depends only on Alpaca *market-data* access, obtained fresh from the shared
AlpacaConnection every cycle - never a fixed client built at startup, since the
connection is only populated after POST /api/v1/alpaca/connect and can be None at
any time (before connecting, or after a disconnect/restart). This loop never
imports or touches AlpacaTradeAdapter or RiskManager: structurally, there is no
code path here that can place an order.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.engine.rationale import RationaleGenerator
from app.engine.screener import build_scan_universe, detect_crossover_signal
from app.engine.suggestion_store import SuggestionStore
from app.engine.watchlist_store import WatchlistStore
from app.security.alpaca_session import AlpacaConnection

logger = logging.getLogger(__name__)

_BAR_HISTORY_DAYS = 120


@dataclass
class ScanLoopConfig:
    interval_seconds: int = 300
    most_active_top: int = 10
    movers_top: int = 10
    min_score: float = 60.0


class SuggestionScanLoop:
    def __init__(
        self,
        connection: AlpacaConnection,
        watchlist_store: WatchlistStore,
        suggestion_store: SuggestionStore,
        rationale_generator: RationaleGenerator,
        config: ScanLoopConfig | None = None,
    ):
        self._connection = connection
        self._watchlist_store = watchlist_store
        self._suggestion_store = suggestion_store
        self._rationale_generator = rationale_generator
        self._config = config or ScanLoopConfig()

    async def run_once(self) -> None:
        session = self._connection.get()
        if session is None:
            logger.info("Suggestion scan skipped: no Alpaca account connected.")
            return

        market_client = session.market_data_client

        watchlist_symbols = [item.symbol for item in self._watchlist_store.list()]
        most_active = [t.symbol for t in market_client.get_most_active(top=self._config.most_active_top)]
        movers = market_client.get_movers(top=self._config.movers_top)
        mover_symbols = [m.symbol for m in (*movers.gainers, *movers.losers)]

        candidates = build_scan_universe(watchlist_symbols, most_active, mover_symbols)
        if not candidates:
            return

        start = datetime.now(UTC) - timedelta(days=_BAR_HISTORY_DAYS)
        symbols = [candidate.symbol for candidate in candidates]
        bars_by_symbol = market_client.get_bars_multi(symbols, start=start)

        for candidate in candidates:
            signal = detect_crossover_signal(
                candidate, bars_by_symbol.get(candidate.symbol, []), min_score=self._config.min_score
            )
            if signal is None:
                continue

            if self._suggestion_store.exists_for_today(signal.symbol, signal.direction.value):
                continue

            rationale = await self._rationale_generator.generate(signal)
            self._suggestion_store.create(signal, rationale)

    async def run_forever(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.exception("Suggestion scan cycle failed; will retry next interval.")
            await asyncio.sleep(self._config.interval_seconds)
