import csv
import io
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import status as http_status

from app.dependencies import get_suggestion_store
from app.engine.suggestion_store import SuggestionStore
from app.models.domain import Suggestion, SuggestionStatus
from app.security.access_token import require_access_token

router = APIRouter(
    prefix="/api/v1/suggestions", tags=["suggestions"], dependencies=[Depends(require_access_token)]
)

_CSV_HEADER = [
    "id",
    "symbol",
    "direction",
    "price",
    "score",
    "sma_fast",
    "sma_slow",
    "rsi14",
    "volume_ratio",
    "triggered_rules",
    "sources",
    "rationale",
    "status",
    "generated_at",
    "updated_at",
]


def _parse_status_filter(raw_status: str) -> SuggestionStatus | None:
    if raw_status == "all":
        return None
    try:
        return SuggestionStatus(raw_status)
    except ValueError as error:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid status '{raw_status}'. Use 'pending', 'dismissed', or 'all'.",
        ) from error


@router.get("", response_model=list[Suggestion])
def list_suggestions(
    status: str = Query(default="pending"),
    symbol: str | None = Query(default=None),
    store: SuggestionStore = Depends(get_suggestion_store),
) -> list[Suggestion]:
    return store.list_all(symbol=symbol, status=_parse_status_filter(status))


@router.get("/export")
def export_suggestions_csv(
    hours: float | None = Query(default=None, gt=0, description="Only include suggestions from the last N hours."),
    store: SuggestionStore = Depends(get_suggestion_store),
) -> Response:
    since = datetime.now(UTC) - timedelta(hours=hours) if hours is not None else None
    filename = f"suggestions_last_{int(hours)}h.csv" if hours is not None else "suggestions_all.csv"

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_CSV_HEADER)

    for row in store.list_all(since=since):
        writer.writerow(
            [
                row.id,
                row.symbol,
                row.direction.value,
                row.price,
                row.score,
                row.indicators.sma_fast,
                row.indicators.sma_slow,
                row.indicators.rsi14,
                row.indicators.volume_ratio,
                ";".join(row.triggered_rules),
                ";".join(source.value for source in row.sources),
                row.rationale or "",
                row.status.value,
                row.generated_at.isoformat(),
                row.updated_at.isoformat(),
            ]
        )

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/{suggestion_id}/dismiss", response_model=Suggestion)
def dismiss_suggestion(
    suggestion_id: int, store: SuggestionStore = Depends(get_suggestion_store)
) -> Suggestion:
    result = store.dismiss(suggestion_id)
    if result is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Suggestion not found.")
    return result
