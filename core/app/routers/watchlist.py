from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_watchlist_store
from app.engine.watchlist_store import WatchlistStore
from app.models.domain import WatchlistAddRequest, WatchlistItem
from app.security.access_token import require_access_token

router = APIRouter(
    prefix="/api/v1/watchlist", tags=["watchlist"], dependencies=[Depends(require_access_token)]
)


@router.get("", response_model=list[WatchlistItem])
def list_watchlist(store: WatchlistStore = Depends(get_watchlist_store)) -> list[WatchlistItem]:
    return store.list()


@router.post("", response_model=WatchlistItem, status_code=status.HTTP_201_CREATED)
def add_to_watchlist(
    body: WatchlistAddRequest, store: WatchlistStore = Depends(get_watchlist_store)
) -> WatchlistItem:
    return store.add(body.symbol)


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(symbol: str, store: WatchlistStore = Depends(get_watchlist_store)) -> None:
    if not store.remove(symbol):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Symbol not found in watchlist.")
