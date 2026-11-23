# Data lokal

Harga harian diambil otomatis dari Yahoo Finance dan disimpan di PostgreSQL (lihat README utama). Folder ini hanya untuk CSV cadangan saat tidak ada internet.

Jika diperlukan, taruh file asli `BBCA_BBRI_BMRI_BBNI_combined.csv` di sini lalu jalankan `python -m app.market.importer`. Baseline terverifikasi berisi 9.605 baris pada 10 Oktober 2016 hingga 8 Oktober 2026, dan jumlahnya cocok dengan data Yahoo setelah hari libur bursa dibuang.

Jalankan migrasi skema sebelum mengimpor CSV. File data kerja di direktori ini dikecualikan dari Git.

Pengumpul dataset berita (`app/dataset/`) menyimpan database di `banking_news.db`, ekspor di `exports/`, dan log di `logs/` dalam folder ini.
