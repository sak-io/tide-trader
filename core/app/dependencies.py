from fastapi import HTTPException, Request, WebSocket, status

from app.adapters.alpaca_data import MarketDataHub
from app.adapters.alpaca_market import AlpacaMarketDataClient
from app.adapters.alpaca_trade import AlpacaTradeAdapter
from app.engine.risk_manager import RiskManager

_NOT_CONNECTED_DETAIL = "Alpaca account not connected. Connect your Alpaca account to continue."


def get_trade_adapter(request: Request) -> AlpacaTradeAdapter:
    session = request.app.state.alpaca_connection.get()
    if session is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONNECTED_DETAIL)
    return session.trade_adapter


def get_risk_manager(request: Request) -> RiskManager:
    return request.app.state.risk_manager


def get_market_data_hub(websocket: WebSocket) -> MarketDataHub:
    return websocket.app.state.market_data_hub


def get_market_data_client(request: Request) -> AlpacaMarketDataClient:
    session = request.app.state.alpaca_connection.get()
    if session is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_NOT_CONNECTED_DETAIL)
    return session.market_data_client
