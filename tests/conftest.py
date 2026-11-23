from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ["NEWS_SYNC_ENABLED"] = "0"
os.environ["PRICE_SYNC_ENABLED"] = "0"
os.environ["SENTIMENT_ENABLED"] = "0"

import pytest

from app import db
import app.market.models  # noqa: F401

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def engine():
    engine = db.configure("sqlite://")
    db.Base.metadata.create_all(engine)
    yield engine
    db.Base.metadata.drop_all(engine)


@pytest.fixture()
def session(engine):
    s = db.get_session_factory()()
    yield s
    s.close()


@pytest.fixture()
def sample_csv() -> Path:
    return FIXTURES / "prices_sample.csv"
