import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.alpaca_data import MarketDataHub, build_stream_runner
from app.config import get_settings
from app.engine.rationale import AnthropicMessagesClient, RationaleGenerator
from app.engine.risk_manager import RiskManager
from app.engine.scan_loop import ScanLoopConfig, SuggestionScanLoop
from app.engine.state_store import StateStore
from app.engine.suggestion_store import SuggestionStore
from app.engine.watchlist_store import WatchlistStore
from app.routers import account, alpaca_connection, market, orders, stream, suggestions, watchlist
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

    app.state.watchlist_store = WatchlistStore(settings.db_path)
    app.state.suggestion_store = SuggestionStore(settings.db_path)

    anthropic_client = (
        AnthropicMessagesClient(settings.anthropic_api_key) if settings.anthropic_api_key else None
    )
    rationale_generator = RationaleGenerator(client=anthropic_client, model=settings.anthropic_model)

    app.state.suggestion_scan_loop = SuggestionScanLoop(
        connection=app.state.alpaca_connection,
        watchlist_store=app.state.watchlist_store,
        suggestion_store=app.state.suggestion_store,
        rationale_generator=rationale_generator,
        config=ScanLoopConfig(
            interval_seconds=settings.scan_interval_seconds,
            most_active_top=settings.scan_most_active_top,
            movers_top=settings.scan_movers_top,
            min_score=settings.scan_min_score,
        ),
    )

    scan_loop_task: asyncio.Task | None = None
    if settings.enable_suggestion_scanner:
        scan_loop_task = asyncio.create_task(app.state.suggestion_scan_loop.run_forever())

    yield

    if stream_runner is not None:
        stream_runner.stop()

    if scan_loop_task is not None:
        scan_loop_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scan_loop_task


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
    app.include_router(suggestions.router)
    app.include_router(watchlist.router)

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover - process entrypoint, not exercised by tests
    import uvicorn

    settings = get_settings()
    # Bound to localhost by default: this API can place real (paper) orders and
    # is meant to be called only by the Electron app running on the same machine.
    uvicorn.run("app.main:app", host=settings.host, port=settings.port)
