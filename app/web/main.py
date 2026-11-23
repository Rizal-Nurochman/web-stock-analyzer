"""Aplikasi FastAPI: API harga, berita live dengan sentimen IndoBERT, fundamental, dan hasil build React.

Berita, sentimen, dan fundamental hanya ada di memori proses; tidak disimpan ke database.

Jalankan (satu worker, loopback):
    uvicorn app.web.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    FRONTEND_DIST,
    news_retention_days,
    news_sync_enabled,
    news_sync_interval_seconds,
    price_sync_enabled,
    price_sync_interval_seconds,
    sentiment_enabled,
    sentiment_model_id,
)
from app.db import get_session_factory
from app.fundamental.service import FundamentalService
from app.market.sync import PriceSyncer
from app.news.live import LiveNewsService
from app.news.model import DisabledSentiment, IndoBertSentiment
from app.web import routes_fundamental, routes_market, routes_news

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def build_live_news() -> LiveNewsService:
    model = IndoBertSentiment(sentiment_model_id()) if sentiment_enabled() else DisabledSentiment()
    return LiveNewsService(model, interval_seconds=news_sync_interval_seconds(),
                           retention_days=news_retention_days())


@asynccontextmanager
async def lifespan(app: FastAPI):
    live = getattr(app.state, "live_news", None) or build_live_news()
    app.state.live_news = live
    price_syncer = getattr(app.state, "price_syncer", None) or PriceSyncer(
        get_session_factory(), interval_seconds=price_sync_interval_seconds()
    )
    app.state.price_syncer = price_syncer
    fundamentals = getattr(app.state, "fundamentals", None) or FundamentalService()
    app.state.fundamentals = fundamentals

    # Model dimuat di thread latar (beberapa detik sampai menit) agar dashboard langsung terbuka.
    # Artikel yang masuk sebelum model siap dinilai pada putaran berikutnya.
    if live.model.status == "pending":
        def load_model() -> None:
            live.model.load()
            # Jangan menunggu putaran berikutnya (5 menit): nilai artikel yang sudah masuk sekarang.
            live.score_pending()

        threading.Thread(target=load_model, name="sentiment-model", daemon=True).start()

    tasks = []
    if price_sync_enabled():
        tasks.append(asyncio.create_task(price_syncer.run_forever(), name="price-sync"))
    if news_sync_enabled():
        tasks.append(asyncio.create_task(live.run_forever(), name="news-live"))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        live.client.close()
        await fundamentals.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="Web Stock Analyzer", version="0.1.0", lifespan=lifespan)
    app.include_router(routes_market.router)
    app.include_router(routes_news.router)
    app.include_router(routes_fundamental.router)

    @app.get("/api/{rest:path}", include_in_schema=False)
    def unknown_api(rest: str):
        return JSONResponse({"detail": "Endpoint tidak ditemukan"}, status_code=404)

    index = FRONTEND_DIST / "index.html"
    if (FRONTEND_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = (FRONTEND_DIST / path).resolve()
        if path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        if index.exists():
            return FileResponse(index)
        return JSONResponse(
            {"detail": "Build frontend belum ada. Jalankan: cd frontend && npm run build"},
            status_code=503,
        )

    return app


app = create_app()
