from collections.abc import Callable

from alpaca.common.exceptions import APIError
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.adapters.alpaca_trade import AlpacaTradeAdapter
from app.models.domain import AlpacaConnectRequest, AlpacaStatus
from app.security.access_token import require_access_token
from app.security.alpaca_session import AlpacaConnection, AlpacaCredentials

router = APIRouter(prefix="/api/v1/alpaca", tags=["alpaca"], dependencies=[Depends(require_access_token)])

CredentialProber = Callable[[str, str, bool], AlpacaTradeAdapter]


def get_credential_prober() -> CredentialProber:
    """Builds the throwaway adapter used to validate a candidate credential pair
    before it's ever handed to the global AlpacaConnection.

    A separate FastAPI dependency (rather than calling
    `AlpacaTradeAdapter.from_credentials` directly in the route) so tests can
    substitute a fake prober and never hit real Alpaca.
    """
    return AlpacaTradeAdapter.from_credentials


def get_alpaca_connection(request: Request) -> AlpacaConnection:
    return request.app.state.alpaca_connection


def _redact(detail: str, secret_key: str) -> str:
    """Defense in depth: never let the raw secret reach an HTTP response body, even
    if some future Alpaca error message happened to echo request input back."""
    if secret_key and secret_key in detail:
        return detail.replace(secret_key, "***")
    return detail


@router.post("/connect", response_model=AlpacaStatus)
def connect(
    body: AlpacaConnectRequest,
    request: Request,
    connection: AlpacaConnection = Depends(get_alpaca_connection),
    prober: CredentialProber = Depends(get_credential_prober),
) -> AlpacaStatus:
    paper = request.app.state.settings.alpaca_paper
    probe_adapter = prober(body.api_key_id, body.secret_key, paper)

    try:
        probe_adapter.get_account()
    except APIError as error:
        try:
            reason = error.message
        except (KeyError, ValueError):
            # APIError.message parses `self._error` as JSON and indexes into it -
            # fall back to the raw string if that shape doesn't hold.
            reason = str(error)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_redact(reason, body.secret_key),
        ) from error

    connection.connect(AlpacaCredentials(api_key_id=body.api_key_id, secret_key=body.secret_key), paper)
    return AlpacaStatus(connected=True)


@router.get("/status", response_model=AlpacaStatus)
def get_status(connection: AlpacaConnection = Depends(get_alpaca_connection)) -> AlpacaStatus:
    return AlpacaStatus(connected=connection.is_connected())


@router.delete("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(connection: AlpacaConnection = Depends(get_alpaca_connection)) -> None:
    connection.disconnect()
