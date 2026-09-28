"""In-memory-only Alpaca credential handling.

Nothing in this module ever touches SQLite, a keyring, or disk. The credential lives
only in this process's memory for as long as the process runs after a user connects
it via POST /api/v1/alpaca/connect - a backend restart wipes it and requires
reconnecting. This is a single global slot (this laptop's one user), not a per-user
registry: multi-user/hosted deployment is explicitly out of scope for this phase.
"""

import threading
from dataclasses import dataclass

from app.adapters.alpaca_market import AlpacaMarketDataClient
from app.adapters.alpaca_trade import AlpacaTradeAdapter


@dataclass(frozen=True)
class AlpacaCredentials:
    api_key_id: str
    secret_key: str

    def __repr__(self) -> str:
        return f"AlpacaCredentials(api_key_id={self.api_key_id!r}, secret_key='***')"


@dataclass
class AlpacaSession:
    credentials: AlpacaCredentials
    trade_adapter: AlpacaTradeAdapter
    market_data_client: AlpacaMarketDataClient


class AlpacaConnection:
    """One global slot (this laptop's one user), not a per-user registry."""

    def __init__(self) -> None:
        self._session: AlpacaSession | None = None
        self._lock = threading.Lock()

    def connect(self, credentials: AlpacaCredentials, paper: bool) -> None:
        session = AlpacaSession(
            credentials=credentials,
            trade_adapter=AlpacaTradeAdapter.from_credentials(
                credentials.api_key_id, credentials.secret_key, paper
            ),
            market_data_client=AlpacaMarketDataClient.from_credentials(
                credentials.api_key_id, credentials.secret_key
            ),
        )
        with self._lock:
            self._session = session

    def get(self) -> AlpacaSession | None:
        with self._lock:
            return self._session

    def disconnect(self) -> None:
        with self._lock:
            self._session = None

    def is_connected(self) -> bool:
        with self._lock:
            return self._session is not None
