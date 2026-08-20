from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.analytics import AnalyticsRepository
from app.schemas.analytics import DashboardResponse, MetadataResponse

router = APIRouter(tags=["analytics"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("/meta", response_model=MetadataResponse)
def metadata(session: DatabaseSession):
    return AnalyticsRepository(session).metadata()


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    session: DatabaseSession,
    start_date: date | None = None,
    end_date: date | None = None,
    store_id: str | None = None,
    top_limit: int = Query(default=10, ge=1, le=20),
):
    try:
        return AnalyticsRepository(session).dashboard(
            start_date=start_date,
            end_date=end_date,
            store_id=store_id,
            top_limit=top_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/data-quality")
def data_quality(session: DatabaseSession):
    return AnalyticsRepository(session).quality_snapshot()
