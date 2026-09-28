from app.security.alpaca_session import AlpacaConnection, AlpacaCredentials


def test_credentials_repr_never_includes_the_raw_secret():
    credentials = AlpacaCredentials(api_key_id="PKTEST", secret_key="do-not-leak-me")

    rendered = repr(credentials)

    assert "PKTEST" in rendered
    assert "do-not-leak-me" not in rendered
    assert "***" in rendered


def test_connection_starts_disconnected():
    connection = AlpacaConnection()

    assert connection.is_connected() is False
    assert connection.get() is None


def test_connect_populates_a_session_built_from_credentials():
    connection = AlpacaConnection()
    credentials = AlpacaCredentials(api_key_id="PKTEST", secret_key="supersecret")

    connection.connect(credentials, paper=True)

    session = connection.get()
    assert session is not None
    assert session.credentials == credentials
    assert connection.is_connected() is True


def test_disconnect_clears_the_session():
    connection = AlpacaConnection()
    connection.connect(AlpacaCredentials(api_key_id="PKTEST", secret_key="supersecret"), paper=True)

    connection.disconnect()

    assert connection.is_connected() is False
    assert connection.get() is None
