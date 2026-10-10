def test_list_starts_empty(watchlist_api_client):
    client, _ = watchlist_api_client
    response = client.get("/api/v1/watchlist")
    assert response.status_code == 200
    assert response.json() == []


def test_add_normalizes_and_persists_the_symbol(watchlist_api_client):
    client, store = watchlist_api_client

    response = client.post("/api/v1/watchlist", json={"symbol": " aapl "})

    assert response.status_code == 201
    assert response.json()["symbol"] == "AAPL"
    assert [item.symbol for item in store.list()] == ["AAPL"]


def test_add_rejects_an_empty_symbol(watchlist_api_client):
    client, _ = watchlist_api_client
    response = client.post("/api/v1/watchlist", json={"symbol": ""})
    assert response.status_code == 422


def test_add_is_idempotent_for_a_duplicate_symbol(watchlist_api_client):
    client, store = watchlist_api_client

    client.post("/api/v1/watchlist", json={"symbol": "AAPL"})
    client.post("/api/v1/watchlist", json={"symbol": "AAPL"})

    assert len(store.list()) == 1


def test_remove_existing_symbol_returns_204(watchlist_api_client):
    client, _ = watchlist_api_client
    client.post("/api/v1/watchlist", json={"symbol": "AAPL"})

    response = client.delete("/api/v1/watchlist/AAPL")

    assert response.status_code == 204
    assert client.get("/api/v1/watchlist").json() == []


def test_remove_missing_symbol_returns_404(watchlist_api_client):
    client, _ = watchlist_api_client
    response = client.delete("/api/v1/watchlist/ZZZZ")
    assert response.status_code == 404
