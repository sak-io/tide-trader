import app.engine.screener as screener_module
from app.engine.screener import (
    ScanCandidate,
    _composite_score,
    _in_healthy_rsi_zone,
    build_scan_universe,
    detect_crossover_signal,
    rsi,
    sma,
    volume_ratio,
)
from app.models.domain import SignalDirection, SignalSource
from tests.fakes import crossover_bars

# --- sma ---------------------------------------------------------------------


def test_sma_averages_the_last_n_values():
    assert sma([1.0, 2.0, 3.0, 4.0], 2) == 3.5


def test_sma_returns_none_when_not_enough_data():
    assert sma([1.0, 2.0], 5) is None


def test_sma_returns_none_for_non_positive_period():
    assert sma([1.0, 2.0, 3.0], 0) is None


# --- rsi -----------------------------------------------------------------------


def test_rsi_returns_none_when_not_enough_data():
    assert rsi([100.0] * 10, period=14) is None


def test_rsi_is_100_when_there_are_no_losses():
    closes = [100.0] * 14 + [101.0]
    assert rsi(closes, period=14) == 100.0


def test_rsi_is_zero_when_there_are_no_gains():
    closes = [100.0] * 14 + [99.0]
    assert rsi(closes, period=14) == 0.0


def test_rsi_is_50_for_a_perfectly_balanced_single_up_and_down_move():
    # period=2: one +1 gain, one -1 loss -> avg_gain == avg_loss == 0.5 -> RS=1 -> RSI=50
    assert rsi([100.0, 101.0, 100.0], period=2) == 50.0


# --- volume_ratio ----------------------------------------------------------------


def test_volume_ratio_divides_latest_by_the_average():
    volumes = [100.0, 100.0, 100.0, 300.0]
    assert volume_ratio(volumes, period=4) == 2.0


def test_volume_ratio_returns_none_when_not_enough_data():
    assert volume_ratio([100.0], period=20) is None


def test_volume_ratio_returns_none_when_average_is_zero():
    assert volume_ratio([0.0] * 20, period=20) is None


# --- build_scan_universe ------------------------------------------------------


def test_build_scan_universe_dedupes_and_normalizes_case():
    candidates = build_scan_universe(
        watchlist_symbols=["aapl"], most_active_symbols=["MSFT"], mover_symbols=["msft", "TSLA"]
    )

    by_symbol = {c.symbol: c.sources for c in candidates}
    assert set(by_symbol) == {"AAPL", "MSFT", "TSLA"}
    assert by_symbol["AAPL"] == {SignalSource.watchlist}
    assert by_symbol["MSFT"] == {SignalSource.alpaca}
    assert by_symbol["TSLA"] == {SignalSource.alpaca}


def test_build_scan_universe_keeps_both_source_tags_for_dual_membership():
    candidates = build_scan_universe(
        watchlist_symbols=["AAPL"], most_active_symbols=["AAPL"], mover_symbols=[]
    )

    assert len(candidates) == 1
    assert candidates[0].sources == {SignalSource.watchlist, SignalSource.alpaca}


def test_build_scan_universe_is_empty_for_no_input():
    assert build_scan_universe([], [], []) == []


# --- detect_crossover_signal ---------------------------------------------------


def test_detect_crossover_signal_returns_none_with_insufficient_history():
    candidate = ScanCandidate(symbol="AAPL", sources={SignalSource.watchlist})
    signal = detect_crossover_signal(candidate, crossover_bars(count=10))
    assert signal is None


def test_detect_crossover_signal_returns_none_when_no_crossover_occurs():
    candidate = ScanCandidate(symbol="AAPL", sources={SignalSource.watchlist})
    flat_bars = crossover_bars(jump_price=100.0)  # no actual jump -> no crossover
    assert detect_crossover_signal(candidate, flat_bars) is None


def test_detect_crossover_signal_detects_a_golden_cross_and_scores_it():
    candidate = ScanCandidate(symbol="AAPL", sources={SignalSource.watchlist})
    bars = crossover_bars(direction="bullish")

    signal = detect_crossover_signal(candidate, bars)

    assert signal is not None
    assert signal.symbol == "AAPL"
    assert signal.direction == SignalDirection.bullish
    assert signal.price == 200.0
    # 50 base + 20 volume confirmation + 0 RSI (RSI is 100, outside the 45-65
    # healthy-trend zone) + 15 gap (capped, gap is ~2.94% >> the 0.5% cap) = 85.0
    assert signal.score == 85.0
    assert signal.indicators.sma_fast == 105.0
    assert signal.indicators.sma_slow == 102.0
    assert "golden_cross_sma20_sma50" in signal.triggered_rules
    assert "volume_confirmation" in signal.triggered_rules
    assert "rsi_healthy_trend" not in signal.triggered_rules
    assert signal.sources == [SignalSource.watchlist]


def test_detect_crossover_signal_detects_a_death_cross_and_scores_it():
    candidate = ScanCandidate(symbol="AAPL", sources={SignalSource.alpaca})
    bars = crossover_bars(direction="bearish")

    signal = detect_crossover_signal(candidate, bars)

    assert signal is not None
    assert signal.direction == SignalDirection.bearish
    assert signal.price == 100.0
    assert signal.score == 85.0
    assert "death_cross_sma20_sma50" in signal.triggered_rules


def test_detect_crossover_signal_returns_none_below_min_score():
    candidate = ScanCandidate(symbol="AAPL", sources={SignalSource.watchlist})
    bars = crossover_bars(direction="bullish")

    assert detect_crossover_signal(candidate, bars, min_score=90) is None


def test_detect_crossover_signal_adds_the_rsi_bonus_when_in_the_healthy_zone(monkeypatch):
    monkeypatch.setattr(screener_module, "rsi", lambda closes, period=14: 55.0)
    candidate = ScanCandidate(symbol="AAPL", sources={SignalSource.watchlist})
    bars = crossover_bars(direction="bullish")

    signal = detect_crossover_signal(candidate, bars)

    assert signal is not None
    assert signal.indicators.rsi14 == 55.0
    assert "rsi_healthy_trend" in signal.triggered_rules
    # 50 base + 20 volume + 15 rsi + 15 gap (capped) = 100
    assert signal.score == 100.0


# --- _composite_score / _in_healthy_rsi_zone (direct unit tests) ---------------


def test_composite_score_adds_the_rsi_bonus_when_in_the_healthy_zone():
    score = _composite_score(
        SignalDirection.bullish, volume_ratio_value=1.0, rsi_value=55.0, crossover_gap_pct=0.0
    )
    assert score == 65.0  # 50 base + 15 rsi bonus, no volume/gap bonus


def test_composite_score_skips_the_volume_bonus_below_threshold():
    score = _composite_score(
        SignalDirection.bullish, volume_ratio_value=1.0, rsi_value=None, crossover_gap_pct=0.0
    )
    assert score == 50.0


def test_in_healthy_rsi_zone_uses_the_bearish_range_for_bearish_signals():
    assert _in_healthy_rsi_zone(SignalDirection.bearish, 45.0) is True
    assert _in_healthy_rsi_zone(SignalDirection.bearish, 60.0) is False


def test_signal_carries_the_date_of_the_bar_it_fired_on():
    bars = crossover_bars("bullish")
    signal = detect_crossover_signal(ScanCandidate("AAPL", {SignalSource.watchlist}), bars)
    assert signal.bar_date == bars[-1].timestamp.date()


def test_drop_incomplete_bar_removes_todays_bar_until_the_session_closes():
    from datetime import UTC, datetime

    from app.engine.screener import drop_incomplete_bar

    bars = crossover_bars("bullish")
    last_day = bars[-1].timestamp  # midnight UTC == the ET trading date
    midday = datetime(last_day.year, last_day.month, last_day.day, 17, 0, tzinfo=UTC)  # 13:00 ET
    evening = datetime(last_day.year, last_day.month, last_day.day, 23, 0, tzinfo=UTC)  # 19:00 ET
    next_day = midday.replace(day=midday.day + 1)

    assert drop_incomplete_bar(bars, midday) == bars[:-1]
    assert drop_incomplete_bar(bars, evening) == bars
    assert drop_incomplete_bar(bars, next_day) == bars
    assert drop_incomplete_bar([], midday) == []
