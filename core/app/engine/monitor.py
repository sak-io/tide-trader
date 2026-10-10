"""Outcome tracking for suggestions: did the hypothetical trade plan work?

Pure evaluation logic plus a thin runner. For each open suggestion, daily bars
after the signal day are replayed in order against its stop/target. If a single
bar touches both, the stop wins (the conservative assumption - intraday order is
unknown). A suggestion with no resolution after `max_age_days` expires at the
last close. Nothing here places or simulates orders on a broker; it only labels
rows in the suggestion history.
"""

import logging
from datetime import UTC, datetime

from app.engine.suggestion_store import SuggestionStore
from app.models.domain import HistoricalBar, SignalDirection, Suggestion, SuggestionOutcome
from app.security.alpaca_session import AlpacaConnection

logger = logging.getLogger(__name__)

MAX_AGE_DAYS = 10


def evaluate(
    suggestion: Suggestion,
    bars: list[HistoricalBar],
    now: datetime,
    max_age_days: int = MAX_AGE_DAYS,
) -> tuple[SuggestionOutcome, float | None, datetime | None, float | None]:
    """Returns (outcome, outcome_price, outcome_at, last_price)."""
    # Compare against the bar the signal fired on, not the wall clock: a signal generated
    # in the evening has a next-day UTC date but its first tradable session is still ahead.
    signal_day = suggestion.bar_date or suggestion.generated_at.date()
    later = sorted((b for b in bars if b.timestamp.date() > signal_day), key=lambda b: b.timestamp)
    bullish = suggestion.direction == SignalDirection.bullish
    last_price = later[-1].close if later else None

    stop, target = suggestion.stop_price, suggestion.target_price
    for bar in later:
        if stop is not None and (bar.low <= stop if bullish else bar.high >= stop):
            # A gap through the stop fills at the open, not at the stop price.
            fill = min(bar.open, stop) if bullish else max(bar.open, stop)
            return SuggestionOutcome.stopped, fill, bar.timestamp, last_price
        if target is not None and (bar.high >= target if bullish else bar.low <= target):
            return SuggestionOutcome.target_hit, target, bar.timestamp, last_price

    if (now - suggestion.generated_at).days >= max_age_days:
        return SuggestionOutcome.expired, last_price or suggestion.price, now, last_price
    return SuggestionOutcome.open, None, None, last_price


class SuggestionMonitor:
    def __init__(
        self, connection: AlpacaConnection, store: SuggestionStore, max_age_days: int = MAX_AGE_DAYS
    ):
        self._connection = connection
        self._store = store
        self._max_age_days = max_age_days

    def run_once(self) -> int:
        """Resolve/refresh every open suggestion. Returns how many changed outcome."""
        session = self._connection.get()
        open_rows = self._store.list_open()
        if session is None or not open_rows:
            return 0

        now = datetime.now(UTC)
        start = min(row.generated_at for row in open_rows)
        bars_by_symbol = session.market_data_client.get_bars_multi(
            sorted({row.symbol for row in open_rows}), start=start
        )

        resolved = 0
        for row in open_rows:
            outcome, price, at, last = evaluate(
                row, bars_by_symbol.get(row.symbol, []), now, self._max_age_days
            )
            self._store.record_outcome(row.id, outcome, price, at, last)
            if outcome != SuggestionOutcome.open:
                resolved += 1
        return resolved
