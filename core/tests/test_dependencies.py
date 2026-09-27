from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.dependencies import (
    get_market_data_client,
    get_market_data_hub,
    get_risk_manager,
    get_trade_adapter,
)


def test_get_trade_adapter_reads_from_app_state():
    fake_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(trade_adapter="adapter-sentinel")))
    assert get_trade_adapter(fake_request) == "adapter-sentinel"


def test_get_trade_adapter_raises_503_when_not_configured():
    fake_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(trade_adapter=None)))
    with pytest.raises(HTTPException) as exc_info:
        get_trade_adapter(fake_request)
    assert exc_info.value.status_code == 503


def test_get_risk_manager_reads_from_app_state():
    fake_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(risk_manager="risk-sentinel")))
    assert get_risk_manager(fake_request) == "risk-sentinel"


def test_get_market_data_hub_reads_from_app_state():
    fake_websocket = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(market_data_hub="hub-sentinel")))
    assert get_market_data_hub(fake_websocket) == "hub-sentinel"


def test_get_market_data_client_reads_from_app_state():
    fake_request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(market_data_client="market-client-sentinel"))
    )
    assert get_market_data_client(fake_request) == "market-client-sentinel"


def test_get_market_data_client_raises_503_when_not_configured():
    fake_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(market_data_client=None)))
    with pytest.raises(HTTPException) as exc_info:
        get_market_data_client(fake_request)
    assert exc_info.value.status_code == 503
