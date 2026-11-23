"""Antarmuka model sentimen per pasangan artikel-emiten.

Tidak ada model bawaan. Selama belum ada model yang dikonfigurasi, predicted_sentiment
dibiarkan kosong. Label manusia disimpan terpisah di manual_sentiment (lihat labels.py).

Contoh memasang model (mis. IndoBERT yang sudah di-fine-tune untuk sentimen per target):

    class MyModel:
        name = "indobert-tbsa-v1"
        def predict(self, title, content, stock_code, stock_name):
            ...
            return "positive", 0.91

    apply_model(db, MyModel())
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select

from app.dataset.database.session import Database
from app.dataset.models.schema import Article, ArticleStock

LABELS = ("positive", "negative", "neutral")


class SentimentModel(Protocol):
    name: str

    def predict(self, title: str, content: str, stock_code: str, stock_name: str) -> tuple[str, float]:
        """Sentimen terhadap emiten tertentu, bukan sentimen umum artikel."""


def apply_model(db: Database, model: SentimentModel, only_missing: bool = True) -> int:
    count = 0
    with db.write() as s:
        query = select(ArticleStock, Article).join(Article, ArticleStock.article_id == Article.article_id)
        if only_missing:
            query = query.where(ArticleStock.predicted_sentiment.is_(None))
        for pair, article in s.execute(query):
            label, confidence = model.predict(article.title, article.content, pair.stock_code, pair.stock_name)
            if label not in LABELS:
                raise ValueError(f"Label model tidak valid: {label!r}")
            pair.predicted_sentiment = label
            pair.sentiment_confidence = float(confidence)
            pair.sentiment_model = model.name
            count += 1
    return count


class IndoBertTargetModel:
    """Adapter model IndoBERT dashboard (app/news/model.py) untuk dataset penelitian.

    Sama seperti dashboard: model hanya membaca judul dan kalimat yang menyebut emiten
    tersebut, sehingga hasilnya sentimen terhadap target, bukan sentimen umum artikel.
    """

    _TO_EN = {"positif": "positive", "netral": "neutral", "negatif": "negative"}

    def __init__(self, model_id: str):
        from app.news.model import IndoBertSentiment

        self._model = IndoBertSentiment(model_id)
        self._model.load()
        if not self._model.ready:
            raise RuntimeError(f"Model {model_id} gagal dimuat: {self._model.error}")
        self.name = f"{model_id} (kalimat target)"

    def predict(self, title: str, content: str, stock_code: str, stock_name: str) -> tuple[str, float]:
        from app.dataset.services.relevance import target_sentences

        sentences = target_sentences(stock_code, title, content) or [title]
        prediction = self._model.predict(sentences)
        return self._TO_EN[prediction.label], prediction.confidence
