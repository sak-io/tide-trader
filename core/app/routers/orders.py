from fastapi import APIRouter, Depends, HTTPException, status

from app.adapters.alpaca_trade import AlpacaTradeAdapter
from app.dependencies import get_risk_manager, get_trade_adapter
from app.engine.risk_manager import RiskManager, RiskViolation
from app.models.domain import (
    KillSwitchAction,
    KillSwitchRequest,
    KillSwitchStatus,
    OrderRequest,
    OrderResponse,
)

router = APIRouter(prefix="/api/v1", tags=["orders"])


@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    order: OrderRequest,
    adapter: AlpacaTradeAdapter = Depends(get_trade_adapter),
    risk_manager: RiskManager = Depends(get_risk_manager),
) -> OrderResponse:
    reference_price = order.limit_price or adapter.get_latest_price(order.symbol)
    account = adapter.get_account()

    try:
        risk_manager.validate_order(
            symbol=order.symbol,
            qty=order.qty,
            price=reference_price,
            current_equity=account.equity,
        )
    except RiskViolation as violation:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=violation.message) from violation

    return adapter.submit_order(order)


@router.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_order(order_id: str, adapter: AlpacaTradeAdapter = Depends(get_trade_adapter)) -> None:
    adapter.cancel_order(order_id)


@router.post("/kill-switch", response_model=KillSwitchStatus)
def set_kill_switch(
    body: KillSwitchRequest,
    risk_manager: RiskManager = Depends(get_risk_manager),
) -> KillSwitchStatus:
    if body.action == KillSwitchAction.activate:
        state = risk_manager.activate_kill_switch(reason=body.reason)
    else:
        state = risk_manager.reset_kill_switch()

    return KillSwitchStatus(kill_switch_active=state.kill_switch_active, reason=state.kill_switch_reason)
