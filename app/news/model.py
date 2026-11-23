"""Sentimen per emiten dengan model IndoBERT lokal.

Model klasifikasi tiga kelas (positif/netral/negatif) dijalankan hanya pada kalimat yang
menyebut emiten tersebut (judul + kalimat isi), lalu probabilitasnya dirata-rata. Dengan
begitu satu artikel bisa positif untuk satu bank dan negatif untuk bank lain.

Model bawaan: intanm/indonesian_financial_sentiment_analysis (IndoBERT base p1 yang
di-fine-tune untuk sentimen keuangan, lisensi MIT). Dipilih setelah dibandingkan pada 12
kalimat berita keuangan berlabel: 7/12 benar, sedangkan dua model sentimen umum
(crypter70/IndoBERT, w11wo/RoBERTa) hanya 3/12 karena menilai hampir semua berita netral.
Hasilnya tetap prediksi, bukan label kebenaran; ganti lewat env SENTIMENT_MODEL.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

log = logging.getLogger(__name__)

LABELS = ("positif", "netral", "negatif")
MAX_SENTENCES = 8
MAX_TOKENS = 256


@dataclass(frozen=True)
class Prediction:
    label: str
    confidence: float
    sentences: int


def _normalize_label(raw: str, index: int, fallback: dict[int, str]) -> str:
    name = raw.lower()
    if name.startswith("pos"):
        return "positif"
    if name.startswith("neu"):
        return "netral"
    if name.startswith("neg"):
        return "negatif"
    if index in fallback:
        return fallback[index]
    raise ValueError(f"Label model tidak dikenali: {raw}")


class IndoBertSentiment:
    """Memuat model sekali di thread latar; inferensi dijaga kunci agar aman antar-thread."""

    # Pemetaan LABEL_n hanya dipakai bila config model tidak memberi nama kelas
    # (konvensi SmSA/IndoNLU: 0=positif, 1=netral, 2=negatif).
    INDEX_FALLBACK = {0: "positif", 1: "netral", 2: "negatif"}

    def __init__(self, model_id: str):
        self.model_id = model_id
        self.status = "pending"  # pending | loading | ready | error | disabled
        self.error: str | None = None
        self._lock = threading.Lock()
        self._tokenizer = None
        self._model = None
        self._labels: list[str] = []

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def load(self) -> None:
        self.status = "loading"
        try:
            import torch  # noqa: F401  (dicek lebih awal agar pesan galatnya jelas)
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(self.model_id)
            model = AutoModelForSequenceClassification.from_pretrained(self.model_id)
            model.eval()
            id2label = model.config.id2label
            labels = [_normalize_label(id2label[i], i, self.INDEX_FALLBACK) for i in range(len(id2label))]
            if sorted(labels) != sorted(LABELS):
                raise ValueError(f"Model harus tiga kelas positif/netral/negatif, dapat {labels}")
            self._tokenizer, self._model, self._labels = tokenizer, model, labels
            self.status = "ready"
            log.info("Model sentimen %s siap (%s)", self.model_id, labels)
        except Exception as exc:  # torch/transformers tidak terpasang atau model gagal diunduh
            self.status = "error"
            self.error = f"{type(exc).__name__}: {exc}"[:300]
            log.error("Model sentimen gagal dimuat: %s", self.error)

    def predict(self, sentences: list[str]) -> Prediction | None:
        if not self.ready or not sentences:
            return None
        import torch

        batch = sentences[:MAX_SENTENCES]
        with self._lock, torch.no_grad():
            encoded = self._tokenizer(batch, padding=True, truncation=True, max_length=MAX_TOKENS,
                                      return_tensors="pt")
            probs = torch.softmax(self._model(**encoded).logits, dim=-1).mean(dim=0)
        index = int(probs.argmax())
        return Prediction(self._labels[index], round(float(probs[index]), 3), len(batch))


class DisabledSentiment:
    model_id = "dimatikan"
    status = "disabled"
    error = "SENTIMENT_ENABLED=0"
    ready = False

    def load(self) -> None:
        pass

    def predict(self, sentences: list[str]) -> Prediction | None:
        return None
