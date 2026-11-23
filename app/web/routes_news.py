from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.config import news_sync_enabled
from app.market.service import has_session
from app.news import service
from app.news.live import LiveNewsService
from app.web.deps import get_session, valid_ticker
from app.web.schemas import ArticleOut, CoverageOut, FeedOut, FeedsOut, ModelOut, NewsOut, WindowOut

router = APIRouter(prefix="/api", tags=["news"])


def get_live(request: Request) -> LiveNewsService:
    return request.app.state.live_news


@router.get("/news/{ticker}", response_model=NewsOut)
def news(
    ticker: str = Depends(valid_ticker),
    session_date: date | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
    session: Session = Depends(get_session),
    live: LiveNewsService = Depends(get_live),
):
    if session_date is None:
        result = service.latest_news(live, ticker, limit)
    else:
        if not has_session(session, ticker, session_date):
            raise HTTPException(
                status_code=404,
                detail=f"Sesi {session_date.isoformat()} tidak ada dalam data harga {ticker}",
            )
        result = service.session_news(live, session, ticker, session_date, limit)

    return NewsOut(
        ticker=ticker,
        mode="session" if session_date else "latest",
        session_date=session_date,
        status=result.status,
        reason=result.reason,
        window=(
            WindowOut(start=result.window.start, end=result.window.end,
                      previous_session=result.previous_session)
            if result.window else None
        ),
        coverage=CoverageOut(earliest_article_at=result.snapshot.earliest_article_at,
                             observed_since=result.snapshot.observed_since),
        articles=[ArticleOut(**article.__dict__) for article in result.articles],
        summary=result.summary,
    )


def _payload(live: LiveNewsService) -> FeedsOut:
    model = live.model
    return FeedsOut(
        syncing=live.running,
        auto_sync=news_sync_enabled(),
        interval_seconds=live.interval_seconds,
        retention_days=live.retention.days,
        last_run_finished_at=live.last_run_finished_at,
        next_run_at=live.next_run_at,
        model=ModelOut(id=model.model_id, status=model.status, error=model.error),
        feeds=[
            FeedOut(id=s.key, name=s.name, publisher=s.name, url=s.homepage, status=s.status,
                    last_attempt_at=s.last_attempt_at, last_success_at=s.last_success_at,
                    first_observed_at=s.first_observed_at, last_error=s.last_error,
                    last_item_count=s.last_item_count, last_new_count=s.last_new_count)
            for s in live.source_states()
        ],
    )


@router.get("/feeds/status", response_model=FeedsOut)
def feeds_status(live: LiveNewsService = Depends(get_live)):
    return _payload(live)


@router.post("/feeds/sync", response_model=FeedsOut)
async def feeds_sync(live: LiveNewsService = Depends(get_live)):
    """Picu satu putaran pemantauan sekarang. Putaran yang sedang berjalan tidak ditumpuk."""
    await live.run_once()
    return _payload(live)
