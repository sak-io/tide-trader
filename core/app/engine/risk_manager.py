import threading
from datetime import date
from typing import Callable

from app.engine.state_store import RiskState, StateStore


class RiskViolation(Exception):
    """Raised when an order fails a pre-trade risk check."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class RiskManager:
    """Deterministic pre-trade risk checks, backed by persisted state.

    All state (kill switch, daily start-of-day equity) is read from and written
    to the injected StateStore on every call, so it survives process restarts
    and stays correct if multiple RiskManager instances share one store.
    """

    def __init__(
        self,
        state_store: StateStore,
        max_position_dollars: float,
        daily_loss_limit_pct: float,
        clock: Callable[[], date] | None = None,
    ):
        self._store = state_store
        self.max_position_dollars = max_position_dollars
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self._clock = clock or date.today
        # FastAPI runs sync route handlers in a thread pool, so concurrent
        # requests can genuinely interleave here - this serializes every
        # read-check-write against risk state so two orders can't both pass
        # a check before either one's write is visible to the other.
        self._lock = threading.Lock()

    def _today(self) -> str:
        return self._clock().isoformat()

    def _roll_day_if_needed(self, state: RiskState, current_equity: float) -> RiskState:
        today = self._today()
        if state.day != today:
            state.day = today
            state.day_start_equity = current_equity
        return state

    def is_kill_switch_active(self) -> bool:
        return self._store.load().kill_switch_active

    def activate_kill_switch(self, reason: str | None = None) -> RiskState:
        with self._lock:
            state = self._store.load()
            state.kill_switch_active = True
            state.kill_switch_reason = reason
            self._store.save(state)
            return state

    def reset_kill_switch(self) -> RiskState:
        with self._lock:
            state = self._store.load()
            state.kill_switch_active = False
            state.kill_switch_reason = None
            self._store.save(state)
            return state

    def current_drawdown_pct(self, current_equity: float) -> float:
        state = self._store.load()
        if not state.day_start_equity:
            return 0.0
        return (state.day_start_equity - current_equity) / state.day_start_equity

    def validate_order(
        self,
        symbol: str,
        qty: float,
        price: float,
        current_equity: float | None = None,
    ) -> None:
        """Raise RiskViolation if the order must not proceed.

        If `current_equity` is supplied, this also rolls the daily-drawdown
        tracker forward and auto-activates the kill switch the moment the
        configured daily loss limit is breached.
        """
        with self._lock:
            state = self._store.load()

            if state.kill_switch_active:
                raise RiskViolation("Kill switch is active; all trading is halted.")

            notional = qty * price
            if notional > self.max_position_dollars:
                raise RiskViolation(
                    f"Order notional ${notional:,.2f} for {symbol} exceeds max position size "
                    f"of ${self.max_position_dollars:,.2f}."
                )

            if current_equity is None:
                return

            state = self._roll_day_if_needed(state, current_equity)

            if state.day_start_equity:
                drawdown = (state.day_start_equity - current_equity) / state.day_start_equity
                if drawdown >= self.daily_loss_limit_pct:
                    state.kill_switch_active = True
                    state.kill_switch_reason = (
                        f"Daily loss limit of {self.daily_loss_limit_pct:.1%} exceeded "
                        f"(drawdown {drawdown:.1%})"
                    )
                    self._store.save(state)
                    raise RiskViolation(state.kill_switch_reason)

            state.last_equity = current_equity
            self._store.save(state)
