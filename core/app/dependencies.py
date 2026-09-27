from fastapi import HTTPException, Request, WebSocket, status

from app.adapters.alpaca_data import MarketDataHub
from app.adapters.alpaca_market import AlpacaMarketDataClient
from app.adapters.alpaca_trade import AlpacaTradeAdapter
from app.engine.risk_manager import RiskManager

_NOT_CONFIGURED_DETAIL = "Alpaca credentials are not configured. Set ALPACA_API_KEY_ID and ALPACA_SECRET_KEY."


def get_trade_adapter(request: Request) -> AlpacaTradeAdapter:
    adapter = request.app.state.trade_adapter
    if adapter is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONFIGURED_DETAIL)
    return adapter


def get_risk_manager(request: Request) -> RiskManager:
    return request.app.state.risk_manager


def get_market_data_hub(websocket: WebSocket) -> MarketDataHub:
    return websocket.app.state.market_data_hub


def get_market_data_client(request: Request) -> AlpacaMarketDataClient:
    client = request.app.state.market_data_client
    if client is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONFIGURED_DETAIL)
    return client
