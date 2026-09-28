from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.adapters.alpaca_market import AlpacaMarketDataClient
from app.dependencies import get_market_data_client
from app.models.domain import ActiveTicker, HistoricalBar, MarketMovers
from app.security.access_token import require_access_token

router = APIRouter(prefix="/api/v1/market", tags=["market"], dependencies=[Depends(require_access_token)])


@router.get("/most-active", response_model=list[ActiveTicker])
def get_most_active(
    top: int = Query(default=10, ge=1, le=100),
    client: AlpacaMarketDataClient = Depends(get_market_data_client),
) -> list[ActiveTicker]:
    return client.get_most_active(top=top)


@router.get("/movers", response_model=MarketMovers)
def get_movers(
    top: int = Query(default=10, ge=1, le=100),
    client: AlpacaMarketDataClient = Depends(get_market_data_client),
) -> MarketMovers:
    return client.get_movers(top=top)


@router.get("/bars/{symbol}", response_model=list[HistoricalBar])
def get_bars(
    symbol: str,
    timeframe: str = Query(default="1Day"),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=10000),
    client: AlpacaMarketDataClient = Depends(get_market_data_client),
) -> list[HistoricalBar]:
    try:
        return client.get_bars(symbol, timeframe=timeframe, start=start, end=end, limit=limit)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
