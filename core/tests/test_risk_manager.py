import threading
import time
from datetime import date

import pytest

from app.engine.risk_manager import RiskManager, RiskViolation
from app.engine.state_store import StateStore


def make_manager(tmp_path, max_dollars: float = 5000.0, daily_loss_pct: float = 0.03, clock=None) -> RiskManager:
    store = StateStore(tmp_path / "state.db")
    return RiskManager(store, max_position_dollars=max_dollars, daily_loss_limit_pct=daily_loss_pct, clock=clock)


def test_order_exceeding_max_dollar_threshold_raises(tmp_path):
    manager = make_manager(tmp_path, max_dollars=1000.0)

    with pytest.raises(RiskViolation, match="exceeds max position size"):
        manager.validate_order(symbol="AAPL", qty=10, price=200.0)  # notional 2000 > 1000


def test_valid_order_passes(tmp_path):
    manager = make_manager(tmp_path, max_dollars=5000.0)

    manager.validate_order(symbol="AAPL", qty=10, price=200.0)  # notional 2000, within limit


def test_kill_switch_blocks_subsequent_orders_immediately(tmp_path):
    manager = make_manager(tmp_path)
    manager.activate_kill_switch(reason="manual halt")

    with pytest.raises(RiskViolation, match="Kill switch is active"):
        manager.validate_order(symbol="AAPL", qty=1, price=10.0)


def test_reset_kill_switch_allows_orders_again(tmp_path):
    manager = make_manager(tmp_path)
    manager.activate_kill_switch()
    manager.reset_kill_switch()

    manager.validate_order(symbol="AAPL", qty=1, price=10.0)  # should not raise
    assert manager.is_kill_switch_active() is False


def test_kill_switch_state_persists_across_manager_instances(tmp_path):
    """A new RiskManager backed by the same SQLite file must see a previously-activated kill switch."""
    db_path = tmp_path / "state.db"

    store_a = StateStore(db_path)
    manager_a = RiskManager(store_a, max_position_dollars=5000.0, daily_loss_limit_pct=0.03)
    manager_a.activate_kill_switch(reason="persisted halt")

    store_b = StateStore(db_path)
    manager_b = RiskManager(store_b, max_position_dollars=5000.0, daily_loss_limit_pct=0.03)

    assert manager_b.is_kill_switch_active() is True
    with pytest.raises(RiskViolation):
        manager_b.validate_order(symbol="AAPL", qty=1, price=10.0)


def test_daily_loss_limit_breach_auto_activates_kill_switch(tmp_path):
    fixed_day = date(2026, 9, 26)
    manager = make_manager(tmp_path, daily_loss_pct=0.03, clock=lambda: fixed_day)

    manager.validate_order(symbol="AAPL", qty=1, price=10.0, current_equity=10000.0)
    assert manager.is_kill_switch_active() is False

    with pytest.raises(RiskViolation, match="Daily loss limit"):
        manager.validate_order(symbol="AAPL", qty=1, price=10.0, current_equity=9500.0)  # -5% > 3% limit

    assert manager.is_kill_switch_active() is True


def test_day_rollover_resets_start_of_day_equity(tmp_path):
    current_day = {"value": date(2026, 9, 26)}
    manager = make_manager(tmp_path, daily_loss_pct=0.03, clock=lambda: current_day["value"])

    manager.validate_order(symbol="AAPL", qty=1, price=10.0, current_equity=10000.0)
    assert manager.current_drawdown_pct(9700.0) == pytest.approx(0.03)

    current_day["value"] = date(2026, 9, 27)
    manager.validate_order(symbol="AAPL", qty=1, price=10.0, current_equity=9700.0)

    assert manager.current_drawdown_pct(9700.0) == pytest.approx(0.0)


def test_current_drawdown_pct_is_zero_with_no_history(tmp_path):
    manager = make_manager(tmp_path)
    assert manager.current_drawdown_pct(10000.0) == 0.0


def test_validate_order_serializes_concurrent_calls(tmp_path):
    """Two threads must never be inside the read-check-write section at once.

    Without the lock, concurrent requests could both read the pre-trade state
    before either commits, letting two orders both pass a check that should
    only ever allow one of them through.
    """
    manager = make_manager(tmp_path)

    concurrency = {"current": 0, "max": 0}
    counter_lock = threading.Lock()
    original_load = manager._store.load

    def instrumented_load():
        with counter_lock:
            concurrency["current"] += 1
            concurrency["max"] = max(concurrency["max"], concurrency["current"])
        time.sleep(0.02)  # widen the window so an unsynchronized race would show up
        result = original_load()
        with counter_lock:
            concurrency["current"] -= 1
        return result

    manager._store.load = instrumented_load

    threads = [
        threading.Thread(target=manager.validate_order, kwargs={"symbol": "AAPL", "qty": 1, "price": 10.0})
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert concurrency["max"] == 1
