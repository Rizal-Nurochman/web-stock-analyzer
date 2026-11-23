"""Registri adapter portal. Urutan mengikuti daftar sumber di spesifikasi."""

from app.dataset.scrapers.antara import Antara
from app.dataset.scrapers.bareksa import Bareksa
from app.dataset.scrapers.base import Portal
from app.dataset.scrapers.blocked import Bisnis, MediaIndonesia, TempoBisnis
from app.dataset.scrapers.cnbcindonesia import CNBCIndonesia
from app.dataset.scrapers.cnnindonesia import CNNIndonesia
from app.dataset.scrapers.detik_finance import DetikFinance
from app.dataset.scrapers.finansialku import Finansialku
from app.dataset.scrapers.idxchannel import IDXChannel
from app.dataset.scrapers.infobank import Infobank
from app.dataset.scrapers.investor import InvestorDaily
from app.dataset.scrapers.kabarbursa import KabarBursa
from app.dataset.scrapers.katadata import Katadata
from app.dataset.scrapers.kompas_money import KompasMoney
from app.dataset.scrapers.kontan import Kontan
from app.dataset.scrapers.liputan6 import Liputan6
from app.dataset.scrapers.republika import Republika

PORTALS: dict[str, type[Portal]] = {
    cls.key: cls
    for cls in (
        CNBCIndonesia, Kontan, Bisnis, Katadata, InvestorDaily, Bareksa, IDXChannel, KabarBursa,
        KompasMoney, DetikFinance, CNNIndonesia, TempoBisnis, Antara, MediaIndonesia, Liputan6,
        Republika, Infobank, Finansialku,
    )
}


def get_portal(key: str) -> Portal:
    if key not in PORTALS:
        raise KeyError(f"Portal tidak dikenal: {key}. Pilihan: {', '.join(PORTALS)}")
    return PORTALS[key]()
