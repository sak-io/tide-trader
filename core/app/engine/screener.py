"""Pure-Python technical screener - no pandas/numpy.

MVP indicator set, computed on daily bars:

1. SMA(20)/SMA(50) crossover (trigger): a golden cross (fast crosses above slow
   between the last two bars) is bullish, a death cross is bearish. No crossover on
   the latest bar means no signal at all.
2. RSI(14), Wilder-smoothed (confirmation).
3. Volume ratio: latest_volume / SMA(volume, 20) (confirmation).

A signal is only ever emitted when a crossover actually fires on the latest bar -
RSI and volume never trigger a signal by themselves, they only adjust its score.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from app.models.domain import (
    HistoricalBar,
    IndicatorSnapshot,
    Signal,
    SignalDirection,
    SignalSource,
)

_SMA_FAST_PERIOD = 20
_SMA_SLOW_PERIOD = 50
_RSI_PERIOD = 14
_VOLUME_SMA_PERIOD = 20
_ATR_PERIOD = 14
_STOP_ATR_MULT = 1.5
_TARGET_ATR_MULT = 3.0

_VOLUME_RATIO_THRESHOLD = 1.5
_BULLISH_RSI_ZONE = (45.0, 65.0)
_BEARISH_RSI_ZONE = (35.0, 55.0)
_GAP_FULL_SCORE_PCT = 0.5

_MIN_BARS_REQUIRED = _SMA_SLOW_PERIOD + 1


def sma(values: list[float], period: int) -> float | None:
    """Simple moving average of the last `period` values, or None if there isn't enough data."""
    if len(values) < period or period <= 0:
        return None
    return sum(values[-period:]) / period


def rsi(closes: list[float], period: int = _RSI_PERIOD) -> float | None:
    """Wilder-smoothed RSI over `closes`. None if there isn't enough data."""
    if len(closes) < period + 1:
        return None

    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    relative_strength = avg_gain / avg_loss
    return 100 - (100 / (1 + relative_strength))


def volume_ratio(volumes: list[float], period: int = _VOLUME_SMA_PERIOD) -> float | None:
    """latest_volume / SMA(volume, period). None if there isn't enough data or the average is zero."""
    average = sma(volumes, period)
    if not average:
        return None
    return volumes[-1] / average


def atr(bars: list[HistoricalBar], period: int = _ATR_PERIOD) -> float | None:
    """Wilder-smoothed average true range. None if there isn't enough data."""
    if len(bars) < period + 1:
        return None
    true_ranges = [
        max(bar.high - bar.low, abs(bar.high - prev.close), abs(bar.low - prev.close))
        for prev, bar in zip(bars, bars[1:], strict=False)
    ]
    value = sum(true_ranges[:period]) / period
    for true_range in true_ranges[period:]:
        value = (value * (period - 1) + true_range) / period
    return value


def trade_plan(
    direction: SignalDirection, entry: float, atr_value: float | None
) -> tuple[float | None, float | None]:
    """(stop, target) at 1.5x / 3x ATR from entry (a 2:1 reward-to-risk plan)."""
    if atr_value is None or atr_value <= 0:
        return None, None
    sign = 1 if direction == SignalDirection.bullish else -1
    stop = entry - sign * _STOP_ATR_MULT * atr_value
    if stop <= 0:
        return None, None
    return stop, entry + sign * _TARGET_ATR_MULT * atr_value


@dataclass
class ScanCandidate:
    symbol: str
    sources: set[SignalSource]


def build_scan_universe(
    watchlist_symbols: list[str],
    most_active_symbols: list[str],
    mover_symbols: list[str],
) -> list[ScanCandidate]:
    """Union the user's watchlist with Alpaca's most-active/movers lists.

    Deduped by uppercased symbol; a symbol appearing in more than one bucket keeps
    every source tag it was found under (never drops one).
    """
    candidates: dict[str, set[SignalSource]] = {}

    for symbol in watchlist_symbols:
        candidates.setdefault(symbol.strip().upper(), set()).add(SignalSource.watchlist)

    for symbol in (*most_active_symbols, *mover_symbols):
        candidates.setdefault(symbol.strip().upper(), set()).add(SignalSource.alpaca)

    return [ScanCandidate(symbol=symbol, sources=sources) for symbol, sources in candidates.items()]


def _composite_score(
    direction: SignalDirection,
    volume_ratio_value: float | None,
    rsi_value: float | None,
    crossover_gap_pct: float,
) -> float:
    score = 50.0

    if volume_ratio_value is not None and volume_ratio_value >= _VOLUME_RATIO_THRESHOLD:
        score += 20.0

    if rsi_value is not None and _in_healthy_rsi_zone(direction, rsi_value):
        score += 15.0

    gap_fraction = min(abs(crossover_gap_pct) / _GAP_FULL_SCORE_PCT, 1.0)
    score += gap_fraction * 15.0

    return score


def _in_healthy_rsi_zone(direction: SignalDirection, rsi_value: float) -> bool:
    zone = _BULLISH_RSI_ZONE if direction == SignalDirection.bullish else _BEARISH_RSI_ZONE
    return zone[0] <= rsi_value <= zone[1]


def detect_crossover_signal(
    candidate: ScanCandidate,
    bars: list[HistoricalBar],
    min_score: float = 60.0,
) -> Signal | None:
    """Detect an SMA(20)/SMA(50) crossover on the latest bar and score it.

    Returns None if there isn't enough history, no crossover fired on the latest
    bar, or the composite score is below `min_score`.
    """
    if len(bars) < _MIN_BARS_REQUIRED:
        return None

    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]

    fast_prev = sma(closes[:-1], _SMA_FAST_PERIOD)
    slow_prev = sma(closes[:-1], _SMA_SLOW_PERIOD)
    fast_now = sma(closes, _SMA_FAST_PERIOD)
    slow_now = sma(closes, _SMA_SLOW_PERIOD)

    if fast_prev is None or slow_prev is None or fast_now is None or slow_now is None:
        # Unreachable given the _MIN_BARS_REQUIRED guard above (both periods are <=
        # _SMA_SLOW_PERIOD), kept as a defensive guard against that invariant changing.
        return None  # pragma: no cover

    direction: SignalDirection | None = None
    triggered_rules: list[str] = []

    if fast_prev <= slow_prev and fast_now > slow_now:
        direction = SignalDirection.bullish
        triggered_rules.append("golden_cross_sma20_sma50")
    elif fast_prev >= slow_prev and fast_now < slow_now:
        direction = SignalDirection.bearish
        triggered_rules.append("death_cross_sma20_sma50")

    if direction is None:
        return None

    rsi_value = rsi(closes)
    volume_ratio_value = volume_ratio(volumes)
    crossover_gap_pct = ((fast_now - slow_now) / slow_now) * 100 if slow_now else 0.0

    if volume_ratio_value is not None and volume_ratio_value >= _VOLUME_RATIO_THRESHOLD:
        triggered_rules.append("volume_confirmation")
    if rsi_value is not None and _in_healthy_rsi_zone(direction, rsi_value):
        triggered_rules.append("rsi_healthy_trend")

    score = _composite_score(direction, volume_ratio_value, rsi_value, crossover_gap_pct)
    if score < min_score:
        return None

    entry = bars[-1].close
    stop_price, target_price = trade_plan(direction, entry, atr(bars))

    return Signal(
        symbol=candidate.symbol,
        direction=direction,
        price=entry,
        score=score,
        stop_price=stop_price,
        target_price=target_price,
        indicators=IndicatorSnapshot(
            sma_fast=fast_now,
            sma_slow=slow_now,
            rsi14=rsi_value if rsi_value is not None else 0.0,
            volume_ratio=volume_ratio_value if volume_ratio_value is not None else 0.0,
        ),
        triggered_rules=triggered_rules,
        sources=sorted(candidate.sources, key=lambda source: source.value),
        generated_at=datetime.now(UTC),
    )
