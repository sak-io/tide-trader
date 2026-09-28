We are building Phase 1 of `tide-trader`: the Python backend core and market gateway.

Read CLAUDE.md first. Then initialize and implement the `core/` backend with the following steps:

1. Environment & Dependencies:
   - Create `core/pyproject.toml` using Poetry (or uv) with: `fastapi`, `uvicorn[standard]`, `alpaca-py`, `pydantic`, `pydantic-settings`, `pytest`, `pytest-asyncio`.
   - Setup `core/.env.example` defining `ALPACA_API_KEY_ID`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER=true`, `MAX_POSITION_DOLLARS=5000.0`, `DAILY_LOSS_LIMIT_PCT=0.03`.

2. Core Implementation:
   - `core/app/config.py`: Load settings using `pydantic_settings.BaseSettings`.
   - `core/app/models/domain.py`: Define Pydantic models for `OrderRequest` (symbol, qty, side, order_type, limit_price), `OrderResponse`, `Position`, and `AccountSummary`.
   - `core/app/engine/risk_manager.py`: Implement deterministic risk validation logic:
     - Check emergency kill switch state.
     - Enforce `qty * price <= MAX_POSITION_DOLLARS`.
     - Track daily drawdown against `DAILY_LOSS_LIMIT_PCT`.
     - Implement `activate_kill_switch()` and `reset_kill_switch()`.
   - `core/app/adapters/alpaca_trade.py`: Wrap `alpaca-py`'s `TradingClient(paper=True)` to fetch balances, get positions, and route validated orders.
   - `core/app/adapters/alpaca_data.py`: Provide an async hub that subscribes to Alpaca's IEX stream and fans out ticks to an internal broadcast queue.
   - `core/app/routers/`:
     - `orders.py`: POST `/api/v1/orders`, DELETE `/api/v1/orders/{id}`, POST `/api/v1/kill-switch`.
     - `account.py`: GET `/api/v1/account`, GET `/api/v1/positions`.
     - `stream.py`: WebSocket endpoint `/ws/live` accepting subscription requests `{"action": "subscribe", "symbols": ["AAPL"]}`.
   - `core/app/main.py`: Assemble FastAPI app with CORS middleware and lifecycle handlers.

3. Testing & Verification:
   - In `core/tests/test_risk_manager.py`, write unit tests verifying:
     1. Orders exceeding the maximum dollar threshold raise HTTP 400.
     2. Valid orders pass risk checks.
     3. Activating the kill switch blocks subsequent orders immediately.
   - Run `pytest` and ensure all tests pass before completing.
