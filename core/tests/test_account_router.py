def test_get_account_returns_summary(api_client):
    response = api_client.get("/api/v1/account")

    assert response.status_code == 200
    body = response.json()
    assert body["equity"] == 10000.0
    assert body["cash"] == 5000.0


def test_get_positions_returns_empty_list_when_none_held(api_client):
    response = api_client.get("/api/v1/positions")

    assert response.status_code == 200
    assert response.json() == []
