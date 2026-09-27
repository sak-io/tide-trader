from fastapi import APIRouter, Depends

from app.adapters.alpaca_trade import AlpacaTradeAdapter
from app.dependencies import get_trade_adapter
from app.models.domain import AccountSummary, Position

router = APIRouter(prefix="/api/v1", tags=["account"])


@router.get("/account", response_model=AccountSummary)
def get_account(adapter: AlpacaTradeAdapter = Depends(get_trade_adapter)) -> AccountSummary:
    return adapter.get_account()


@router.get("/positions", response_model=list[Position])
def get_positions(adapter: AlpacaTradeAdapter = Depends(get_trade_adapter)) -> list[Position]:
    return adapter.get_positions()
