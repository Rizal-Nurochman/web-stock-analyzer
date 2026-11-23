# Web Stock Analyzer

Dashboard lokal untuk demo Kelompok 3. Pengguna memilih BBCA, BBRI, BMRI, atau BBNI, lalu menelusuri candlestick harian, Bollinger Bands, volume, sentimen per artikel, dan metrik fundamental (valuasi, profitabilitas, neraca, arus kas, dividen, pertumbuhan) dari Yahoo Finance.

MVP menggunakan React dan Vite untuk dashboard, FastAPI untuk API, dan PostgreSQL untuk penyimpanan.

- [Requirement MVP, kriteria penerimaan, dan cakupan lanjutan](docs/requirements.md)
- [Arsitektur sistem](docs/architecture.md)
- [Rencana implementasi](docs/superpowers/plans/2026-11-23-mvp.md)
- [Penempatan data lokal](data/README.md)
- [Pengumpul dataset berita untuk analisis sentimen](docs/dataset-collector.md) (`app/dataset/`)

## Menjalankan aplikasi

Prasyarat: Python 3.11+, Node.js 20+, dan PostgreSQL lokal.

### 1. Backend dan database

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt

createdb web_stock_analyzer      # atau buat lewat pgAdmin
set DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/web_stock_analyzer
                                 # PowerShell: $env:DATABASE_URL="..."   bash: export DATABASE_URL=...
alembic upgrade head
python -m app.market.sync        # ambil histori harian dari Yahoo Finance (butuh internet)
```

Harga diambil dari Yahoo Finance (`BBCA.JK`, `BBRI.JK`, `BMRI.JK`, `BBNI.JK`) dan disimpan ke database. Server juga menyinkronkan otomatis saat startup lalu tiap jam, jadi langkah `app.market.sync` di atas hanya mengisi database lebih awal sebelum demo. Saat internet putus, dashboard menampilkan data tersimpan beserta status gagalnya.

Aturan pengambilan:

- Hari libur bursa yang diisi Yahoo dengan candle datar bervolume 0 dibuang. Hasilnya cocok dengan baseline CSV: 2.400 / 2.402 / 2.401 / 2.402 sesi pada 10 Okt 2016 sampai 8 Okt 2026.
- Baris dengan High/Low tidak konsisten terhadap Open/Close (hanya ditemukan sebelum 2008) dikoreksi ke rentangnya dan dicatat jumlahnya.
- Candle hari ini baru disimpan setelah 16.15 WIB, saat sesi sudah final.
- Setiap emiten diganti seluruh serinya dalam satu transaksi agar data Yahoo dan CSV tidak bercampur. Jika Yahoo mengirim jauh lebih sedikit sesi dari yang tersimpan, data lama dipertahankan.

Endpoint chart Yahoo tidak resmi dan bisa membatasi permintaan (HTTP 429). Karena itu permintaan dibuat berurutan dengan jeda 1 detik, dan hasilnya selalu disimpan lokal.

**Cadangan tanpa internet:** `python -m app.market.importer data/BBCA_BBRI_BMRI_BBNI_combined.csv`. Importer memvalidasi seluruh file lebih dulu; satu kesalahan berarti tidak ada baris yang ditulis. Sinkronisasi Yahoo berikutnya akan mengganti seri CSV tersebut.

### 2. Frontend

```bash
cd frontend
npm install
npm run build        # hasil di frontend/dist, disajikan oleh FastAPI
```

### 3. Demo (satu worker, loopback)

```bash
uvicorn app.web.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Buka http://127.0.0.1:8000. Harga disinkronkan saat startup lalu tiap jam. Berita dipantau live tiap 5 menit dari 7 portal (CNBC Indonesia, Kontan, Katadata, Kompas Money, detikFinance, CNN Indonesia, Infobank) lewat news sitemap, lalu sentimennya dinilai per emiten oleh model IndoBERT lokal. Tombol **Perbarui harga** dan **Cek berita sekarang** memicu satu putaran untuk demo.

**Berita dan sentimen tidak disimpan ke database.** Semuanya hanya ada di memori server (7 hari terakhir) dan hilang saat server dihentikan. Setelah server dinyalakan, panel berita terisi dalam 1–3 menit dari artikel yang masih tercantum di news sitemap (±1–5 hari terakhir).

### Model sentimen

Model bawaan [`intanm/indonesian_financial_sentiment_analysis`](https://huggingface.co/intanm/indonesian_financial_sentiment_analysis) (IndoBERT yang di-fine-tune untuk sentimen keuangan, MIT) diunduh otomatis saat server pertama kali jalan (±950 MB, butuh internet sekali), lalu dipakai offline dari cache Hugging Face. Model dijalankan hanya pada kalimat yang menyebut tiap emiten, sehingga satu artikel bisa positif untuk satu bank dan negatif untuk bank lain.

Pada 12 kalimat berita keuangan yang kami uji, model ini benar 7/12. Dua model sentimen umum Indonesia hanya benar 3/12 karena menilai hampir semua berita netral. Kesalahan yang terlihat: kalimat kontras seperti "asing borong BBCA saat saham bank BUMN dilepas" dan beberapa frasa keuangan ("NPL terjaga rendah" dinilai negatif). Persentase keyakinan ditampilkan di setiap label; anggap hasilnya indikator, bukan kepastian.

### Mode pengembangan

Jalankan Uvicorn seperti di atas (boleh dengan `--reload`), lalu `npm run dev` di `frontend/`. Vite di http://localhost:5173 meneruskan `/api` ke port 8000.

## Variabel lingkungan

| Variabel | Bawaan | Fungsi |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/web_stock_analyzer` | Koneksi database. |
| `PRICE_SYNC_ENABLED` | `1` | `0` mematikan pengambilan harga otomatis dari Yahoo Finance. |
| `PRICE_SYNC_INTERVAL_SECONDS` | `3600` | Interval pengecekan harga (minimal 300). |
| `NEWS_SYNC_ENABLED` | `1` | `0` mematikan pemantauan berita live. |
| `NEWS_SYNC_INTERVAL_SECONDS` | `300` | Jeda antarputaran pemantauan (minimal 60). |
| `NEWS_RETENTION_DAYS` | `7` | Lama artikel disimpan di memori server. |
| `SENTIMENT_ENABLED` | `1` | `0` mematikan model; artikel tampil sebagai Belum dinilai. |
| `SENTIMENT_MODEL` | `intanm/indonesian_financial_sentiment_analysis` | ID model Hugging Face tiga kelas (positif/netral/negatif). |

Untuk menyimulasikan sumber gagal, putuskan internet lalu tekan **Cek berita sekarang**: status tiap portal berubah menjadi gagal, sementara berita yang sudah ada di memori tetap tampil.

## Dataset berita untuk analisis sentimen

`app/dataset/` mengumpulkan berita tentang BBRI, BMRI, BBCA, dan BBNI dari 18 portal (15 dapat diakses, 3 menolak akses otomatis) ke SQLite, lalu mengekspornya ke CSV dan JSONL untuk penelitian sentimen berbasis target.

```powershell
.venv\Scripts\python -m app.dataset.main check-sources
.venv\Scripts\python -m app.dataset.main scrape --start 2023-01-01 --end 2023-12-31
.venv\Scripts\python -m app.dataset.main export
.venv\Scripts\python -m app.dataset.main summary --html
```

Konfigurasi, aturan relevansi, skema data, dan laporan integrasi per portal ada di [docs/dataset-collector.md](docs/dataset-collector.md).

## Pengujian

```bash
pytest
```

Tes memakai SQLite dan fixture sintetis di `tests/fixtures/` sehingga tidak butuh PostgreSQL atau internet. Verifikasi jumlah baris per emiten (9.605 total) tetap dilakukan dengan CSV asli melalui keluaran importer.

## Catatan keputusan

- **Sentimen** memakai leksikon keuangan berbahasa Indonesia, hanya pada kalimat yang menyebut emiten tersebut, sehingga satu artikel bisa berlabel berbeda per emiten. Konteks kurang dari 5 kata diberi label *Belum dinilai*. Model akhir menunggu pemeriksaan label manual (R-05).
- **Jendela berita per sesi** dari penutupan sesi sebelumnya (16.00 WIB) sampai penutupan sesi terpilih. Respons membedakan *tidak ada artikel*, *cakupan sebagian* (sebelum feed mulai diamati), dan *konteks belum tersedia* (sebelum arsip tersimpan atau sesi pertama).
- **Desain** mengikuti `Desain.md` (tema gelap "twilight summit") dengan aturan `antislop.md`. Garis punggung di header digambar dari harga penutupan asli emiten aktif.
