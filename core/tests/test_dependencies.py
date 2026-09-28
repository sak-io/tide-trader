from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.dependencies import (
    get_market_data_client,
    get_market_data_hub,
    get_risk_manager,
    get_trade_adapter,
)


def _fake_request(session) -> SimpleNamespace:
    connection = SimpleNamespace(get=lambda: session)
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(alpaca_connection=connection)))


def test_get_trade_adapter_reads_from_the_alpaca_connection_session():
    session = SimpleNamespace(trade_adapter="adapter-sentinel")
    assert get_trade_adapter(_fake_request(session)) == "adapter-sentinel"


def test_get_trade_adapter_raises_503_when_not_connected():
    with pytest.raises(HTTPException) as exc_info:
        get_trade_adapter(_fake_request(None))
    assert exc_info.value.status_code == 503
    assert "not connected" in exc_info.value.detail


def test_get_risk_manager_reads_from_app_state():
    fake_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(risk_manager="risk-sentinel")))
    assert get_risk_manager(fake_request) == "risk-sentinel"


def test_get_market_data_hub_reads_from_app_state():
    fake_websocket = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(market_data_hub="hub-sentinel")))
    assert get_market_data_hub(fake_websocket) == "hub-sentinel"


def test_get_market_data_client_reads_from_the_alpaca_connection_session():
    session = SimpleNamespace(market_data_client="market-client-sentinel")
    assert get_market_data_client(_fake_request(session)) == "market-client-sentinel"


def test_get_market_data_client_raises_503_when_not_connected():
    with pytest.raises(HTTPException) as exc_info:
        get_market_data_client(_fake_request(None))
    assert exc_info.value.status_code == 503
    assert "not connected" in exc_info.value.detail
