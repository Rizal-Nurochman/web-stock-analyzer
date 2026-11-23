# Frontend

Dashboard React + Vite dengan Lightweight Charts. `src/App.jsx` menyimpan emiten aktif, rentang tanggal, dan candle terpilih. `src/features/market/` berisi pemilih emiten, rentang, chart, dan detail candle. `src/features/news/` berisi daftar berita dan status feed.

```bash
npm install
npm run dev     # http://localhost:5173, /api diteruskan ke 127.0.0.1:8000
npm run build   # hasil di dist/, disajikan FastAPI
```

Token warna dan tipografi ada di `src/styles/tokens.css` (dari `Desain.md`). Font Inter dan Inter Tight dibundel lewat `@fontsource` agar demo tetap rapi tanpa internet. Lihat [arsitektur sistem](../docs/architecture.md) untuk kontrak API.
