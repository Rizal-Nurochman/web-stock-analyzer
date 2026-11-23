# Pengumpul Dataset Berita Perbankan

Program di `app/dataset/` mengumpulkan berita berbahasa Indonesia tentang **BBRI, BMRI, BBCA, dan BBNI** untuk penelitian *Target-Based Sentiment Analysis*. Prioritasnya kualitas dan relevansi: artikel yang relevansinya belum pasti dipisahkan ke kategori *review*, dan tidak ada label sentimen otomatis yang dibuat tanpa model.

## Instalasi

```powershell
cd "C:\Users\HP Victus\Desktop\Niel Code\web-stock-analyzer"
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

Database SQLite dibuat otomatis di `data/banking_news.db`. Program ini tidak membutuhkan PostgreSQL.

## Cara menjalankan

Semua perintah dijalankan dari folder proyek.

```powershell
# 1. Daftar portal dan metode aksesnya
.venv\Scripts\python -m app.dataset.main list-sources

# 2. Periksa robots.txt dan akses setiap portal saat ini
.venv\Scripts\python -m app.dataset.main check-sources

# 3. Kumpulkan berita (periode default dari settings.toml: 2023-01-01 s.d. 2026-11-23)
.venv\Scripts\python -m app.dataset.main scrape

#    Pilih portal dan periode tertentu
.venv\Scripts\python -m app.dataset.main scrape --sources detik_finance,kontan --start 2023-01-01 --end 2023-12-31

#    Uji cepat: batasi artikel tersimpan atau unit penemuan per portal
.venv\Scripts\python -m app.dataset.main scrape --sources katadata --start 2024-01-01 --end 2024-01-07 --max-articles 20

# 4. Ekspor dataset (CSV, JSONL, salinan SQLite) ke data/exports/
.venv\Scripts\python -m app.dataset.main export

# 5. Ringkasan di konsol, plus laporan HTML bergrafik di data/exports/summary.html
.venv\Scripts\python -m app.dataset.main summary --html

# 6. Impor label manual dan keputusan review
.venv\Scripts\python -m app.dataset.main import-labels data/exports/banking_news_article_stocks.csv
```

**Melanjutkan proses yang terhenti.** Tekan `Ctrl+C` kapan saja, lalu jalankan ulang perintah yang sama. Tanggal indeks dan file sitemap yang sudah selesai tercatat di tabel `checkpoints`. Setiap URL yang sudah diproses (tersimpan, ditolak, maupun di luar periode) tercatat di `seen_urls`, jadi tidak diunduh ulang. URL yang gagal karena jaringan dicoba lagi maksimal 3 kali di run berikutnya.

**Estimasi waktu.** Jeda minimum 2 detik per domain (lebih lama bila robots.txt meminta). Dari uji langsung, satu hari arsip memakan sekitar 75 detik untuk CNBC (3 kanal), 45 detik untuk Kontan, dan 30 detik untuk detik. Periode penuh 2023–2026 (1.423 hari) memerlukan sekitar 30 jam bila semua portal berjalan paralel. Disarankan menjalankannya per tahun, misalnya `--start 2023-01-01 --end 2023-12-31`, semalaman.

## Konfigurasi

Semua pengaturan ada di [`app/dataset/config/settings.toml`](../app/dataset/config/settings.toml). Periode, lokasi database, jeda permintaan, panjang minimum isi, portal aktif, dan jumlah portal paralel bisa diubah tanpa menyentuh kode. Argumen CLI (`--start`, `--end`, `--sources`, `--db`, `--config`) menimpa nilai di file tersebut. Tanggal memakai zona Asia/Jakarta dan bersifat inklusif.

Kamus emiten, alias, frasa pengecualian, dan kata konteks ada di [`app/dataset/config/keywords.py`](../app/dataset/config/keywords.py).

## Struktur

| Folder | Isi |
|---|---|
| `app/dataset/config/` | `settings.toml`, pemuat konfigurasi, kamus emiten dan konteks |
| `app/dataset/scrapers/` | Satu adapter per portal + `base.py` (helper indeks per tanggal, sitemap, halaman tag, RSS) |
| `app/dataset/services/` | `http.py` (robots.txt, jeda, retry, deteksi blokir), `extraction.py`, `relevance.py`, `dedup.py`, `pipeline.py`, `summary.py`, `labels.py`, `sentiment.py` |
| `app/dataset/models/` | Skema SQLite dan struktur data pipeline |
| `app/dataset/database/` | Koneksi SQLite (WAL) dan repository |
| `app/dataset/exports/` | Penulis CSV, JSONL, dan salinan SQLite |
| `app/dataset/main.py` | Entry point CLI |
| `tests/dataset/` | Tes relevansi, deduplikasi, ekstraksi, klien HTTP, dan pipeline |

Program ini memakai ulang `app/news/canonical.py` (normalisasi URL, termasuk penyatuan artikel ANTARA lintas kanal) dan zona WIB dari `app/config.py`. Database-nya terpisah dari database dashboard.

## Alur per artikel

1. **Penemuan** lewat jalur sah yang tersedia di tiap portal (tabel di bawah).
2. **Prafilter judul/slug** dengan kata kunci lebar (ticker, nama, alias, "saham bank", "himbara", ...). Kandidat dari halaman tag ticker melewati tahap ini.
3. **Unduh** setelah memeriksa robots.txt, dengan jeda per domain dan retry terbatas untuk 429/5xx.
4. **Ekstraksi** isi dengan Trafilatura (tanpa komentar dan tabel), lalu pembersihan baris "Baca juga", iklan, ajakan video, widget, kredit redaksi, dan catatan arsip. Metadata diambil dari JSON-LD dan meta tag, dan tanggal dinormalisasi ke Asia/Jakarta. Halaman dengan isi kurang dari 400 karakter (video, teaser) dibuang. Artikel berbayar (`isAccessibleForFree=false` atau penanda langganan) dicatat sebagai *paywalled* dan tidak ditembus.
5. **Relevansi per emiten** (lihat di bawah).
6. **Deduplikasi** lalu simpan.

## Aturan relevansi

Diterapkan per emiten di [`services/relevance.py`](../app/dataset/services/relevance.py):

- **Pengecualian dulu.** Frasa yang merujuk entitas lain dihapus sebelum menghitung sebutan: BRI/BNI/BCA Syariah, BRI Liga 1, Desa Mandiri, Jalur Mandiri, dan sebagainya.
- **Sebutan kuat** (BBRI, Bank Rakyat Indonesia, Bank BRI, BRI (Persero), ...) selalu dihitung.
- **Alias pendek** (BRI, BNI, BCA, Mandiri berhuruf kapital) hanya dihitung bila kalimatnya memuat konteks perbankan atau pasar modal. Alias yang berulang tanpa konteks dimasukkan ke *review*, tidak dibuang diam-diam.
- **Relevant** bila emiten menjadi objek pembahasan, yaitu disebut di judul, disebut ≥ 3 kali, atau disebut di paragraf pembuka lalu disebut lagi. Selain itu harus teridentifikasi oleh sebutan kuat atau ≥ 2 alias berkonteks, dan artikelnya memuat konteks bisnis/keuangan.
- **Review** untuk sebutan sambil lalu, artikel tanpa konteks bisnis, alias saja, artikel tanpa tanggal terbit, dan konten layanan konsumen (kurs harian per bank, cara setor tunai, syarat/info KUR, biaya admin, promo).
- Setiap pasangan artikel-emiten punya status dan alasannya sendiri. Satu artikel bisa *relevant* untuk BBNI dan *review* untuk BBRI.

## Anti-duplikasi

1. **URL kanonis.** Tabel `seen_urls` dan kolom unik `articles.canonical_url`. Parameter pelacak dibuang, dan ANTARA serta detik disatukan per ID artikel.
2. **Hash isi** (SHA-256 dari isi ternormalisasi) untuk isi identik.
3. **Sindikasi.** Judul ternormalisasi (kemiripan ≥ 0,85, angka di judul harus sama) dan isi (Jaccard shingle 5 kata ≥ 0,6) dalam jendela ±3 hari.

Duplikat **tetap disimpan** dengan sumber masing-masing, ditandai `is_duplicate` dan `duplicate_reason` (`identical_content` atau `syndicated`), serta berbagi `duplicate_group_id`. Contoh dari uji langsung: siaran pers BRI terbit di ANTARA dan IDX Channel, sehingga keduanya masuk satu grup.

## Skema data

**`articles`**: article_id, title, content, source, url, canonical_url, author, published_at (ISO +07:00), scraped_at, category, language, content_hash, title_key, word_count, relevance_status (`relevant`/`review`), duplicate_group_id, is_duplicate, duplicate_reason, discovered_via.

**`article_stocks`** (satu baris per pasangan artikel-emiten, unit analisis TBSA): stock_code, stock_name, relevance, relevance_score, mention_count, in_title, matched_terms, relevance_reasons, **predicted_sentiment, sentiment_confidence, sentiment_model** (kosong sampai ada model), **manual_sentiment** (label manusia, `positive`/`negative`/`neutral`), review_status (`unreviewed`/`reviewed`/`rejected`), reviewer_note.

Tabel pendukung: `seen_urls`, `checkpoints`, `source_status`, `runs`.

### File ekspor (`data/exports/`)

| File | Isi |
|---|---|
| `banking_news_dataset.csv` / `.jsonl` | Dataset utama: artikel relevan, `stock_codes` dan `stock_names` berupa daftar |
| `banking_news_article_stocks.csv` / `.jsonl` | Pasangan artikel-emiten relevan beserta kolom sentimen, siap dianotasi |
| `banking_news_review.csv` / `.jsonl` | Artikel yang perlu diperiksa, lengkap dengan kandidat emiten dan alasannya |
| `banking_news_review_pairs.csv` | Pasangan artikel-emiten yang perlu diperiksa, satu baris per pasangan, siap diisi kolom `relevance` |
| `banking_news_unprocessed.csv` | URL gagal, paywall, tanpa isi, diblokir, atau dilarang robots.txt |
| `banking_news_dataset.sqlite` | Salinan database lengkap |

## Sentimen

Belum ada model sentimen yang dikonfigurasi, jadi `predicted_sentiment` sengaja dibiarkan kosong. Untuk memasang model (misalnya IndoBERT yang di-fine-tune per target), implementasikan antarmuka `SentimentModel` di [`services/sentiment.py`](../app/dataset/services/sentiment.py) lalu panggil `apply_model(db, model)`. Model harus memberi label terhadap **emiten tertentu**, bukan sentimen umum artikel.

Alur anotasi manual:

1. Jalankan `export`.
2. Isi kolom `manual_sentiment` dan `review_status` di `banking_news_article_stocks.csv`. Untuk pasangan yang perlu diperiksa, isi kolom `relevance` (`relevant` atau `irrelevant`) di `banking_news_review_pairs.csv`. Pasangan yang diterima masuk ke dataset utama pada ekspor berikutnya.
3. Jalankan `import-labels`. Nilai yang tidak valid ditolak per baris tanpa mengubah baris lain.

Label sentimen leksikon di dashboard (`app/news/sentiment.py`) tidak dipakai di dataset ini.

## Kepatuhan akses

- robots.txt diperiksa untuk setiap host sebelum setiap permintaan (RFC 9309: robots.txt yang tidak terjangkau berarti semua dilarang). `Crawl-delay` dipatuhi.
- User-Agent jujur (`BankingNewsResearchBot/0.1 ...`). Program tidak menyamar sebagai peramban.
- Respons 401/403/451 dan tantangan Cloudflare dicatat sebagai **diblokir**. Program tidak mencoba melewati paywall, CAPTCHA, login, atau proteksi bot, dan tidak memakai browser automation. Setelah 3 blokir berturut-turut, portal dihentikan.
- Ketentuan penggunaan tiap portal tidak bisa diverifikasi secara otomatis. Sebelum mempublikasikan dataset (teks lengkap artikel), periksa ketentuan hak cipta tiap media. Untuk riset, umumnya aman membagikan metadata, URL, dan label, bukan teks lengkap.

## Laporan integrasi portal

Diuji langsung pada 23 November 2026 dengan artikel sungguhan (periode 14–15 Maret 2023, 5 Agustus 2024, dan 1–23 November 2026).

| Portal | Status | Jalur akses | Hasil uji | Keterbatasan |
|---|---|---|---|---|
| CNBC Indonesia | Tersedia | Indeks per tanggal kanal market, news, research | 2 hari 2023: 20 relevan, 1 review | Halaman video tanpa teks dibuang |
| Kontan | Tersedia | Indeks per tanggal kanal investasi, keuangan | 2 hari 2023: 23 relevan, 1 review | Artikel kurs harian per bank masuk review |
| Katadata | Tersedia | Sitemap bulanan sejak 2021 | 2 hari 2023: 13 relevan, 2 review | |
| Kompas Money | Tersedia | Indeks per tanggal, artikel `?page=all` | 2 hari 2023: 7 relevan, 1 review | |
| Detik Finance | Tersedia | Indeks per tanggal, artikel `?single=1` | 2 hari 2023: 13 relevan, 1 review | |
| CNN Indonesia | Tersedia | Indeks per tanggal kanal ekonomi | 2 hari 2023: 4 relevan | |
| Infobank | Tersedia | Sitemap WordPress | Nov 2026: 31 relevan, 4 review, 1 paywalled | `lastmod` adalah waktu ubah, jadi periode sempit tetap mengunduh artikel lama sekali |
| Investor Daily | Parsial | Halaman tag ticker/nama bank | Nov 2026: 115 relevan, 48 review | Hanya artikel bertag; indeks per tanggal tidak mendukung tanggal lampau |
| ANTARA News | Parsial | Halaman tag + RSS | Nov 2026: 56 relevan, 68 review | Tidak ada sitemap; hanya artikel bertag atau yang muncul di RSS |
| Republika | Parsial | Halaman tag (offset 15) | Nov 2026: 15 relevan, 3 review | Hanya artikel bertag |
| IDX Channel | Parsial | Indeks halaman pertama + sitemap kanal | Nov 2026: 20 relevan, 3 review | ±16 artikel per hari; halaman berikutnya dimuat JavaScript |
| Liputan6 | Parsial | Indeks per tanggal kanal bisnis, saham | 2 hari 2023: 16 relevan, 1 review | robots.txt melarang `?page=`, jadi ±20 artikel per kanal per hari |
| KabarBursa | Parsial | Sitemap kuartalan | Nov 2026: 8 relevan | Arsip mulai 2024 |
| Bareksa | Parsial | Sitemap kategori | Nov 2026: 8 relevan | Hanya ±50 artikel terakhir per kategori |
| Finansialku | Parsial | Sitemap WordPress (Crawl-delay 10 dtk) | 2023: 3 relevan, 2 review (dibatasi 5) | Konten edukasi; artikel terbaru di sitemap sekitar 2024 |
| Bisnis.com | **Tidak terintegrasi** | | HTTP 403, tantangan Cloudflare | robots.txt juga melarang `/rss/`, `/feed/` |
| Tempo Bisnis | **Tidak terintegrasi** | | HTTP 403 untuk halaman, sitemap, dan RSS | |
| Media Indonesia | **Tidak terintegrasi** | | HTTP 403, tantangan Cloudflare | |

Jalankan `check-sources` untuk memeriksa ulang. Status akses bisa berubah sewaktu-waktu.

## Batasan yang perlu diketahui

- **Recall prafilter.** Pada portal indeks dan sitemap, artikel yang judul atau slug-nya tidak menyebut bank sama sekali tidak diunduh, meski isinya mungkin membahas emiten. Ini kompromi agar jumlah permintaan tetap wajar. Portal berbasis tag tidak terkena batasan ini.
- **Aturan relevansi berbasis aturan,** bukan model. Ambang dan kamusnya ada di `keywords.py` dan `relevance.py`. Periksa sampel `banking_news_review.csv` dan sesuaikan bila perlu.
- **Struktur HTML portal bisa berubah.** Jalankan `check-sources` dan uji kecil (`--max-articles`) sebelum run panjang.
