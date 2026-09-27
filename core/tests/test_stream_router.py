import time
from collections.abc import Callable


def wait_until(predicate: Callable[[], bool], timeout: float = 1.0, interval: float = 0.02) -> bool:
    """Poll until predicate() is true - the server processes websocket messages on its
    own portal thread, so state changes aren't visible to the test the instant send_json()
    returns."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_websocket_subscribe_registers_symbol_on_the_hub(stream_client):
    client, hub = stream_client

    with client.websocket_connect("/ws/live") as websocket:
        websocket.send_json({"action": "subscribe", "symbols": ["AAPL"]})

        assert wait_until(lambda: "AAPL" in hub.subscribed_symbols())


def test_websocket_unsubscribe_removes_symbol_while_still_connected(stream_client):
    client, hub = stream_client

    with client.websocket_connect("/ws/live") as websocket:
        websocket.send_json({"action": "subscribe", "symbols": ["AAPL", "MSFT"]})
        assert wait_until(lambda: set(hub.subscribed_symbols()) == {"AAPL", "MSFT"})

        websocket.send_json({"action": "unsubscribe", "symbols": ["AAPL"]})
        assert wait_until(lambda: hub.subscribed_symbols() == ["MSFT"])


def test_disconnect_cleans_up_all_subscriptions(stream_client):
    client, hub = stream_client

    with client.websocket_connect("/ws/live") as websocket:
        websocket.send_json({"action": "subscribe", "symbols": ["AAPL", "MSFT"]})
        assert wait_until(lambda: set(hub.subscribed_symbols()) == {"AAPL", "MSFT"})

    assert wait_until(lambda: hub.subscribed_symbols() == [])


def test_published_tick_is_forwarded_to_the_subscribed_client(stream_client):
    client, hub = stream_client

    with client.websocket_connect("/ws/live") as websocket:
        websocket.send_json({"action": "subscribe", "symbols": ["AAPL"]})
        assert wait_until(lambda: "AAPL" in hub.subscribed_symbols())

        # Uses the same threadsafe path the real Alpaca stream integration uses -
        # `subscribe` above binds the hub to this app's own event loop.
        hub.publish_threadsafe("AAPL", {"type": "trade", "symbol": "AAPL", "price": 101.5})

        message = websocket.receive_json()
        assert message == {"type": "trade", "symbol": "AAPL", "price": 101.5}


def test_two_clients_independently_subscribe_without_interfering(stream_client):
    client, hub = stream_client

    with client.websocket_connect("/ws/live") as ws_a, client.websocket_connect("/ws/live") as ws_b:
        ws_a.send_json({"action": "subscribe", "symbols": ["AAPL"]})
        ws_b.send_json({"action": "subscribe", "symbols": ["MSFT"]})

        assert wait_until(lambda: set(hub.subscribed_symbols()) == {"AAPL", "MSFT"})

    assert wait_until(lambda: hub.subscribed_symbols() == [])
