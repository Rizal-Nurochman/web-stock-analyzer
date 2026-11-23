from app.dataset.services.relevance import article_status, classify


def by_code(matches):
    return {m.code: m for m in matches}


def test_ticker_in_title_with_business_context_is_relevant():
    title = "Laba BBRI Kuartal III Tumbuh 12 Persen, Saham Menguat"
    content = (
        "PT Bank Rakyat Indonesia (Persero) Tbk mencatat laba bersih Rp45 triliun pada kuartal III. "
        "Kinerja kredit mikro menopang pertumbuhan aset. Saham BBRI naik 2 persen di BEI."
    )
    m = by_code(classify(title, content))
    assert m["BBRI"].relevance == "relevant"
    assert article_status(list(m.values())) == "relevant"


def test_multiple_banks_each_get_their_own_relation():
    title = "Saham BBCA dan BMRI Diborong Asing, BBNI Tertekan"
    content = (
        "Investor asing mencatat beli bersih saham BBCA dan BMRI di Bursa Efek Indonesia. "
        "Sementara saham BBNI melemah. Analis menilai valuasi bank besar masih menarik."
    )
    m = by_code(classify(title, content))
    assert set(m) == {"BBCA", "BMRI", "BBNI"}
    assert all(x.relevance == "relevant" for x in m.values())


def test_generic_words_are_not_banks():
    title = "Pemerintah Dorong Desa Mandiri Energi di Jawa Tengah"
    content = ("Program desa mandiri energi menargetkan 100 desa. Warga diajak hidup mandiri. "
               "Kementerian menyiapkan anggaran dan pendampingan.")
    assert classify(title, content) == []


def test_bri_league_and_sharia_subsidiaries_are_excluded():
    title = "Jadwal BRI Liga 1 Pekan Ini"
    content = "Persib menjamu Persija dalam lanjutan BRI Liga 1. Tiket dijual di laman resmi klub."
    assert classify(title, content) == []
    content2 = "BNI Syariah dan BRI Syariah kini bergabung menjadi Bank Syariah Indonesia (BSI) di bursa saham."
    assert classify("Sejarah Merger Bank Syariah", content2) == []


def test_short_alias_without_context_is_not_counted():
    # "BCA" di sini nama penghargaan, kalimatnya tanpa konteks perbankan/pasar.
    assert classify("Pemenang BCA Awards Diumumkan", "Acara digelar di Bali dengan meriah malam ini.") == []


def test_passing_mention_goes_to_review():
    title = "IHSG Ditutup Menguat, Saham Teknologi Memimpin"
    content = (
        "IHSG ditutup menguat 0,8 persen. Saham teknologi seperti GOTO dan BUKA memimpin kenaikan. "
        "Investor asing mencatat net buy Rp500 miliar. Kinerja emiten konsumer juga solid. "
        "Pergerakan pasar dipengaruhi rilis inflasi. Di sektor lain, saham BBCA bergerak stagnan."
    )
    m = by_code(classify(title, content))
    assert m["BBCA"].relevance == "review"
    assert "sebutan sambil lalu" in m["BBCA"].reasons


def test_csr_news_without_business_context_goes_to_review():
    title = "BRI Ajak Keluarga Ikut Fun Run di Jakarta"
    content = ("BRI menggelar lomba lari keluarga di Jakarta. BRI menyiapkan hadiah menarik. "
               "Ribuan peserta datang sejak pagi bersama anak-anak.")
    m = by_code(classify(title, content))
    assert m["BBRI"].relevance == "review"


def test_consumer_service_articles_go_to_review():
    content = ("Nasabah BRI dapat melakukan setor tunai di ATM. Bank Rakyat Indonesia menyediakan layanan "
               "BRImo. Saham BBRI dan kinerja kredit tidak dibahas di sini, hanya cara transaksi rekening.")
    for title in ("Cara Setor Tunai BRI di ATM agar Tidak Gagal",
                  "Intip Kurs Dollar-Rupiah di BRI Jelang Tengah Hari Ini"):
        m = by_code(classify(title, content))
        assert m["BBRI"].relevance == "review", title
        assert any("layanan" in r for r in m["BBRI"].reasons)


def test_product_explainers_review_but_kur_disbursement_stays_relevant():
    content = ("Bank Rakyat Indonesia (BBRI) menyalurkan kredit usaha rakyat. Kinerja penyaluran KUR BRI "
               "mendorong pertumbuhan laba dan aset perseroan. Saham BBRI menguat di bursa.")
    for title in ("Simak Info KUR BRI 2023, Agar Pengajuan Tidak Ditolak!", "Apa Itu CMS BRI? Kenali Fiturnya",
                  "Ketahui Biaya Admin BNI Terbaru", "Mudah! Cara Setor Tunai BCA di ATM"):
        assert all(m.relevance == "review" for m in classify(title, content)), title
    assert by_code(classify("Penyaluran KUR BRI Tembus Rp150 Triliun", content))["BBRI"].relevance == "relevant"


def test_daily_deposit_rate_lists_are_service_content():
    content = ("Bank Rakyat Indonesia (BBRI), Bank Mandiri (BMRI), dan Bank Negara Indonesia (BBNI) "
               "menetapkan suku bunga deposito untuk nasabah. Bank BUMN menjaga likuiditas dan kinerja kredit.")
    title = "Daftar Terbaru Bunga Deposito BRI, BNI & Mandiri per 23 November 2026"
    assert all(m.relevance == "review" for m in classify(title, content))
    policy = "Bank Rakyat Indonesia Naikkan Bunga Deposito Usai BI Rate Naik"
    assert by_code(classify(policy, content))["BBRI"].relevance == "relevant"
