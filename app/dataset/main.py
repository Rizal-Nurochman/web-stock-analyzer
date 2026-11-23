"""Pengumpul berita saham perbankan (BBRI, BMRI, BBCA, BBNI) untuk analisis sentimen.

Contoh:
    python -m app.dataset.main check-sources
    python -m app.dataset.main scrape --sources detik_finance,kontan --start 2023-01-01 --end 2023-01-31
    python -m app.dataset.main export
    python -m app.dataset.main summary --html
    python -m app.dataset.main import-labels data/exports/banking_news_article_stocks.csv
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

from app.dataset.config import Settings, load_settings
from app.dataset.database.session import Database
from app.dataset.scrapers import PORTALS


def _setup_logging(settings: Settings, verbose: bool) -> Path:
    """Semua log ke file; konsol menampilkan progres portal (atau semuanya dengan -v)."""
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = settings.logs_dir / f"dataset-{datetime.now():%Y%m%d-%H%M%S}.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(message)s"))
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
    if not verbose:
        # Hanya logger "dataset" (progres pipeline) yang tampil di konsol.
        console.addFilter(lambda record: record.name == "dataset" or record.levelno >= logging.ERROR)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers[:] = [file_handler, console]
    for noisy in ("httpx", "httpcore", "trafilatura", "htmldate", "charset_normalizer", "courlan"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return log_path


def _sources(arg: str | None, settings: Settings) -> list[str]:
    keys = [k.strip() for k in arg.split(",")] if arg else list(settings.enabled_sources)
    unknown = [k for k in keys if k not in PORTALS]
    if unknown:
        raise SystemExit(f"Portal tidak dikenal: {', '.join(unknown)}. Lihat: list-sources")
    return keys


def _settings(args) -> Settings:
    settings = load_settings(Path(args.config) if args.config else None)
    overrides = {
        "start": date.fromisoformat(args.start) if getattr(args, "start", None) else None,
        "end": date.fromisoformat(args.end) if getattr(args, "end", None) else None,
        "database": Path(args.db) if args.db else None,
        "max_articles_per_source": getattr(args, "max_articles", None),
        "max_units_per_source": getattr(args, "max_units", None),
        "parallel_sources": getattr(args, "parallel", None),
    }
    settings = settings.with_overrides(**overrides)
    if settings.start > settings.end:
        raise SystemExit("--start harus sebelum atau sama dengan --end")
    return settings


def cmd_list_sources(args) -> int:
    for key, cls in PORTALS.items():
        portal = cls()
        flag = "TIDAK TERSEDIA" if portal.blocked_reason else ("PARSIAL" if portal.coverage_note else "")
        print(f"{key:16} {portal.name:26} {flag:14} {portal.access_method}")
    return 0


def cmd_check(args) -> int:
    from app.dataset.services.pipeline import Collector

    settings = _settings(args)
    _setup_logging(settings, args.verbose)
    db = Database(settings.database)
    collector = Collector(settings, db)
    print(f"{'Portal':26} {'Status':12} Catatan")
    for portal, status, note in collector.check_sources(_sources(args.sources, settings)):
        print(f"{portal.name:26} {status:12} {note}")
    return 0


def cmd_scrape(args) -> int:
    from app.dataset.services.pipeline import Collector
    from app.dataset.services.summary import build_summary, format_console

    settings = _settings(args)
    log_path = _setup_logging(settings, args.verbose)
    keys = _sources(args.sources, settings)
    print(f"Periode {settings.start} s.d. {settings.end} | portal: {', '.join(keys)}")
    print(f"Database: {settings.database}\nLog: {log_path}")
    db = Database(settings.database)
    collector = Collector(settings, db)
    try:
        results = collector.run(keys)
    except KeyboardInterrupt:
        print("\nDihentikan. Checkpoint tersimpan; jalankan perintah yang sama untuk melanjutkan.")
        return 130
    finally:
        collector.client.close()

    print("\nHASIL PER PORTAL")
    print(f"{'Portal':16} {'Status':11} {'Temu':>6} {'Unduh':>6} {'Relevan':>7} {'Review':>6} "
          f"{'Dupl.':>5} {'Tdk rel.':>8} {'Gagal':>5}  Catatan")
    for s in results:
        failed = s.failed + s.no_content + s.paywalled + s.blocked
        note = s.stopped_early or s.note
        print(f"{s.source:16} {s.status:11} {s.discovered:6} {s.fetched:6} {s.saved_relevant:7} "
              f"{s.saved_review:6} {s.duplicates:5} {s.irrelevant:8} {failed:5}  {note[:80]}")
    print("\n" + format_console(build_summary(db)))
    return 0


def cmd_export(args) -> int:
    from app.dataset.exports import export_all

    settings = _settings(args)
    db = Database(settings.database)
    out = Path(args.out) if args.out else settings.exports_dir
    formats = tuple(f.strip() for f in args.formats.split(","))
    result = export_all(db, out, formats)
    print(f"Ekspor ke {out}: {result['articles']} artikel relevan, {result['pairs']} pasangan "
          f"artikel-emiten, {result['review']} artikel review, {result['unprocessed']} URL tak terproses")
    for kind, names in result["files"].items():
        print(f"  {kind}: {', '.join(names)}")
    return 0


def cmd_summary(args) -> int:
    from app.dataset.services.summary import build_summary, format_console, write_html

    settings = _settings(args)
    summary = build_summary(Database(settings.database))
    print(format_console(summary))
    if args.html:
        path = write_html(summary, settings.exports_dir / "summary.html")
        print(f"\nLaporan HTML: {path}")
    return 0


def cmd_import_labels(args) -> int:
    from app.dataset.services.labels import import_labels

    settings = _settings(args)
    report = import_labels(Database(settings.database), Path(args.csv))
    print(f"{report.updated} pasangan diperbarui.")
    for error in report.errors[:50]:
        print("  " + error)
    return 1 if report.errors else 0


def cmd_predict_sentiment(args) -> int:
    from app.config import sentiment_model_id
    from app.dataset.services.sentiment import IndoBertTargetModel, apply_model

    settings = _settings(args)
    model_id = args.model or sentiment_model_id()
    print(f"Memuat model {model_id} ...")
    model = IndoBertTargetModel(model_id)
    count = apply_model(Database(settings.database), model, only_missing=not args.all)
    print(f"{count} pasangan artikel-emiten diberi predicted_sentiment oleh {model.name}.")
    print("Label prediksi bukan ground truth; label manusia tetap di manual_sentiment.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.dataset.main", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="Path settings.toml lain")
    parser.add_argument("--db", help="Path database SQLite (menimpa settings)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-sources", help="Daftar portal dan metode aksesnya").set_defaults(func=cmd_list_sources)

    check = sub.add_parser("check-sources", help="Periksa robots.txt dan akses setiap portal")
    check.add_argument("--sources")
    check.add_argument("-v", "--verbose", action="store_true")
    check.set_defaults(func=cmd_check)

    scrape = sub.add_parser("scrape", help="Kumpulkan berita (bisa dilanjutkan bila terhenti)")
    scrape.add_argument("--sources", help="Daftar portal dipisah koma; default dari settings.toml")
    scrape.add_argument("--start", help="YYYY-MM-DD (WIB)")
    scrape.add_argument("--end", help="YYYY-MM-DD (WIB)")
    scrape.add_argument("--max-articles", type=int, help="Batas artikel tersimpan per portal (uji coba)")
    scrape.add_argument("--max-units", type=int, help="Batas unit penemuan (hari/halaman/sitemap) per portal")
    scrape.add_argument("--parallel", type=int, help="Jumlah portal paralel")
    scrape.add_argument("-v", "--verbose", action="store_true")
    scrape.set_defaults(func=cmd_scrape)

    export = sub.add_parser("export", help="Ekspor CSV, JSONL, dan SQLite")
    export.add_argument("--formats", default="csv,jsonl,sqlite")
    export.add_argument("--out", help="Folder tujuan; default storage.exports_dir")
    export.set_defaults(func=cmd_export)

    summary = sub.add_parser("summary", help="Ringkasan hasil pengumpulan")
    summary.add_argument("--html", action="store_true", help="Tulis juga laporan HTML dengan grafik")
    summary.set_defaults(func=cmd_summary)

    predict = sub.add_parser("predict-sentiment",
                             help="Isi predicted_sentiment dengan model IndoBERT (per emiten)")
    predict.add_argument("--model", help="ID model Hugging Face; default SENTIMENT_MODEL")
    predict.add_argument("--all", action="store_true", help="Nilai ulang pasangan yang sudah diprediksi")
    predict.set_defaults(func=cmd_predict_sentiment)

    labels = sub.add_parser("import-labels", help="Impor label manual / keputusan review dari CSV")
    labels.add_argument("csv")
    labels.set_defaults(func=cmd_import_labels)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
