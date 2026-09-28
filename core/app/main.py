import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.alpaca_data import MarketDataHub, build_stream_runner
from app.config import get_settings
from app.engine.risk_manager import RiskManager
from app.engine.state_store import StateStore
from app.routers import account, alpaca_connection, market, orders, stream
from app.security.access_token import load_or_create_access_token
from app.security.alpaca_session import AlpacaConnection


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    app.state.settings = settings
    app.state.access_token = load_or_create_access_token()
    app.state.alpaca_connection = AlpacaConnection()

    loop = asyncio.get_running_loop()
    app.state.market_data_hub = MarketDataHub(loop=loop)

    state_store = StateStore(settings.db_path)
    app.state.risk_manager = RiskManager(
        state_store=state_store,
        max_position_dollars=settings.max_position_dollars,
        daily_loss_limit_pct=settings.daily_loss_limit_pct,
    )

    stream_runner = build_stream_runner(settings, app.state.market_data_hub)
    app.state.stream_runner = stream_runner
    if stream_runner is not None:
        stream_runner.start()

    yield

    if stream_runner is not None:
        stream_runner.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Tide Trader Core", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(orders.router)
    app.include_router(account.router)
    app.include_router(market.router)
    app.include_router(alpaca_connection.router)
    app.include_router(stream.router)

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover - process entrypoint, not exercised by tests
    import uvicorn

    settings = get_settings()
    # Bound to localhost by default: this API can place real (paper) orders and
    # is meant to be called only by the Electron app running on the same machine.
    uvicorn.run("app.main:app", host=settings.host, port=settings.port)
