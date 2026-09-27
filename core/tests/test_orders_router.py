def test_valid_market_order_returns_201(api_client):
    response = api_client.post(
        "/api/v1/orders",
        json={"symbol": "AAPL", "qty": 1, "side": "buy", "order_type": "market"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["symbol"] == "AAPL"
    assert body["status"] == "accepted"


def test_valid_limit_order_returns_201(api_client):
    response = api_client.post(
        "/api/v1/orders",
        json={
            "symbol": "MSFT",
            "qty": 2,
            "side": "sell",
            "order_type": "limit",
            "limit_price": 300.0,
        },
    )

    assert response.status_code == 201
    assert response.json()["order_type"] == "limit"


def test_order_exceeding_max_position_dollars_returns_400(api_client):
    # AAPL priced at 190 in the fake market data client; 100 * 190 = 19000 > 5000 limit
    response = api_client.post(
        "/api/v1/orders",
        json={"symbol": "AAPL", "qty": 100, "side": "buy", "order_type": "market"},
    )

    assert response.status_code == 400
    assert "exceeds max position size" in response.json()["detail"]


def test_kill_switch_blocks_orders_via_api(api_client):
    activate = api_client.post("/api/v1/kill-switch", json={"action": "activate", "reason": "manual halt"})
    assert activate.status_code == 200
    assert activate.json() == {"kill_switch_active": True, "reason": "manual halt"}

    order_response = api_client.post(
        "/api/v1/orders",
        json={"symbol": "AAPL", "qty": 1, "side": "buy", "order_type": "market"},
    )
    assert order_response.status_code == 400
    assert "Kill switch is active" in order_response.json()["detail"]


def test_kill_switch_reset_allows_orders_again(api_client):
    api_client.post("/api/v1/kill-switch", json={"action": "activate"})
    reset = api_client.post("/api/v1/kill-switch", json={"action": "reset"})

    assert reset.status_code == 200
    assert reset.json() == {"kill_switch_active": False, "reason": None}

    order_response = api_client.post(
        "/api/v1/orders",
        json={"symbol": "AAPL", "qty": 1, "side": "buy", "order_type": "market"},
    )
    assert order_response.status_code == 201


def test_cancel_order_returns_204(api_client):
    submit = api_client.post(
        "/api/v1/orders",
        json={"symbol": "AAPL", "qty": 1, "side": "buy", "order_type": "market"},
    )
    order_id = submit.json()["id"]

    response = api_client.delete(f"/api/v1/orders/{order_id}")

    assert response.status_code == 204


def test_limit_order_without_limit_price_is_rejected_by_validation(api_client):
    response = api_client.post(
        "/api/v1/orders",
        json={"symbol": "AAPL", "qty": 1, "side": "buy", "order_type": "limit"},
    )

    assert response.status_code == 422
