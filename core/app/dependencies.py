from fastapi import Request, WebSocket

from app.adapters.alpaca_data import MarketDataHub
from app.adapters.alpaca_market import AlpacaMarketDataClient
from app.adapters.alpaca_trade import AlpacaTradeAdapter
from app.engine.risk_manager import RiskManager


def get_trade_adapter(request: Request) -> AlpacaTradeAdapter:
    return request.app.state.trade_adapter


def get_risk_manager(request: Request) -> RiskManager:
    return request.app.state.risk_manager


def get_market_data_hub(websocket: WebSocket) -> MarketDataHub:
    return websocket.app.state.market_data_hub


def get_market_data_client(request: Request) -> AlpacaMarketDataClient:
    return request.app.state.market_data_client
