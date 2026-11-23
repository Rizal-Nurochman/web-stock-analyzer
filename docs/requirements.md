# Requirement Web Stock Analyzer

## Tujuan dan pengguna

Kelompok 3 mendemokan dashboard di laptop presentasi kepada dosen. Pengguna memilih satu emiten dari BBCA, BBRI, BMRI, dan BBNI, menelusuri harga, volatilitas, dan volume, lalu memeriksa konteks berita serta sentimen terhadap emiten tersebut. Temuan chart bersifat deskriptif dan dapat ditelusuri ke data. Klaim tentang peluang pantulan atau pengaruh berita terhadap harga memerlukan pengujian tersendiri.

Demo dioperasikan kelompok dalam browser lokal. Dosen melihat layar presentasi. Akses mandiri, akun, dan hosting publik berada di luar MVP.

## Requirement MVP

| ID | Kebutuhan | Kriteria penerimaan |
|---|---|---|
| R-01 | Pilih satu dari empat emiten. | Chart, detail, dan panel berita mengikuti emiten yang sama. Pergantian emiten mengosongkan sesi terpilih sebelumnya. |
| R-02 | Jelajahi histori lengkap CSV. | Seluruh 9.605 baris tersedia. Rentang awal tiga bulan dihitung dari tanggal terakhir yang tersedia. Rentang bebas dapat membuka kembali BBCA 2018–2020. Tanggal harga terakhir terlihat di dekat chart. |
| R-03 | Tampilkan candle harian, Bollinger Bands, dan volume. | Harga dan volume berbagi sumbu waktu. Sesi terpilih menampilkan OHLC, volume, dan nilai ketiga band. Band memakai Close, SMA 20 sesi, dan ±2 standar deviasi sampel. Nilai 19 sesi pertama kosong. Mengubah filter tanggal mempertahankan nilai band pada tanggal yang sama. |
| R-04 | Ambil berita secara otomatis. | Saat aplikasi lokal mulai berjalan, sinkronisasi berjalan otomatis dan berulang selama proses aktif. ANTARA Finansial, ANTARA Bursa, dan detikFinance diproses secara independen. Target awal 15 menit mengikuti batas akses tiap sumber. Artikel yang sama tetap satu entri setelah sinkronisasi ulang, termasuk lintas kanal ANTARA. |
| R-05 | Sajikan berita dan sentimen per artikel–emiten. | Artikel relevan menampilkan judul, media, tautan asli, waktu terbit dalam WIB, dan label Positif, Netral, Negatif, atau Belum dinilai. Pemetaan memakai ticker, nama resmi, dan alias yang diperiksa. Artikel yang membahas beberapa emiten dapat memiliki label berbeda per emiten. Gunakan Belum dinilai saat konteks kurang dan periksa sampel dari empat bank secara manual. |
| R-06 | Hubungkan berita dengan sesi jika cakupan memungkinkan. | Panel Berita terbaru mengikuti emiten aktif dan dapat berisi artikel setelah akhir CSV. Saat candle dipilih, gunakan jendela setelah penutupan sesi sebelumnya sampai penutupan sesi terpilih. Bedakan sesi tanpa artikel dari konteks yang belum tersedia karena batas sesi atau cakupan arsip belum diketahui. |
| R-07 | Beri status saat data tertunda. | Tampilkan status dan waktu terakhir berhasil per feed. Uji kegagalan satu feed sambil menjaga artikel tersimpan dan hasil feed lain. Harga, chart, dan berita tersimpan tetap bisa dibuka ketika internet putus selama aplikasi dan PostgreSQL lokal berjalan. |

## Baseline data yang diverifikasi

CSV acuan adalah `BBCA_BBRI_BMRI_BBNI_combined.csv`, dengan rentang **10 Oktober 2016–8 Oktober 2026** pada tiap emiten.

| Emiten | Baris |
|---|---:|
| BBCA | 2.400 |
| BBRI | 2.402 |
| BMRI | 2.401 |
| BBNI | 2.402 |

Ketiga CSV individual BBCA, BBRI, dan BBNI cocok untuk tanggal, OHLC, Adj Close, dan volume. BMRI diperiksa dari file gabungan. Pemeriksaan menemukan nol tanggal duplikat per emiten, nol pelanggaran rentang OHLC, dan nol baris gagal dibaca. Selisih cakupan masih perlu dicocokkan dengan kalender bursa sebelum menyatakan suatu sesi hilang. Saat impor, pertahankan basis CSV dan gunakan Close untuk band. Tandai sesi yang datanya belum tersedia.

## Sumber berita dan batas validasi

- Uji teknis awal mendapatkan 20 entri dari masing-masing kanal ANTARA dan 100 dari detikFinance. Semua entri uji memiliki judul, tautan, waktu terbit, dan cuplikan. Sampel ini belum membuktikan cakupan empat emiten setiap hari atau kedalaman arsip. [ANTARA Finansial](https://www.antaranews.com/rss/ekonomi-finansial.xml) · [ANTARA Bursa](https://www.antaranews.com/rss/ekonomi-bursa.xml) · [detikFinance](https://finance.detik.com/rss)
- Sebelum integrasi, validasi ketentuan penyimpanan dan penayangan metadata. Pilihan model sentimen dan interval akhir mengikuti hasil pengujian sumber serta label. Tampilkan cakupan arsip yang diketahui pada dashboard.

## Pengembangan yang ditunda

- **Histori terbaru.** Lengkapi sesi setelah 8 Oktober 2026 sampai penutupan final terbaru. Bandingkan beberapa sesi tumpang tindih untuk memeriksa penyesuaian aksi korporasi, definisi harga, dan satuan volume.
- **Candle sesi berjalan.** Pertahankan satu candle harian per emiten. Feed harus menyediakan pembukaan, tertinggi, terendah, harga terakhir, volume kumulatif sesi, dan jam kuotasi asli. Tampilkan waktu dalam WIB serta status sementara, final, atau pembaruan tertunda sesuai kondisi. Usulan band sementara memakai 19 penutupan final dan harga terakhir sesi berjalan. Target yang belum divalidasi adalah jeda penyedia hingga 15 menit dan pengecekan setiap satu menit sesuai batas akses.
- **Evaluasi penyedia harga.** Uji langsung `saham-mcp` untuk histori tiga bulan gagal pada keempat emiten. Log jalur Yahoo Finance memuat Too Many Requests. Jalur quote yang diperiksa tidak meneruskan open atau waktu kuotasi asli. GOAPI masih kandidat histori. Snapshot publiknya mendokumentasikan tanggal dan volume tanpa jam kuotasi atau definisi volume kumulatif. Uji berautentikasi ditunda. [saham-mcp](https://github.com/baguskto/saham-mcp) · [Skema GOAPI](https://goapi.io/v1.0.1.yaml)
- **Perluasan analisis.** Keterbukaan resmi, opini media sosial, agregat sentimen, perbandingan antaremiten, parameter indikator yang dapat diubah, dan backtesting. Replay sesi juga berada di luar MVP.

## Skenario penerimaan demo

1. Buka dashboard lokal, pilih BBCA 2018–2020, lalu periksa detail candle dan konsistensi band setelah mengubah rentang.
2. Ganti emiten dan pastikan chart serta berita menunjukkan pilihan baru.
3. Tunjukkan satu sinkronisasi otomatis yang berhasil dari sumber asli, periksa emiten dan tautan artikel, lalu pastikan sinkronisasi ulang tidak menambah duplikat. Jika feed sepi, respons RSS yang direkam dapat mendemokan masuknya artikel baru.
4. Simulasikan satu feed gagal, lalu putuskan internet. Tunjukkan status sumber, histori, dan berita yang sudah tersimpan.

Keputusan teknis React, FastAPI, dan PostgreSQL sejak tahap pertama dicatat di [arsitektur sistem](architecture.md). Urutan pengerjaan ada di [rencana implementasi](superpowers/plans/2026-11-23-mvp.md).
