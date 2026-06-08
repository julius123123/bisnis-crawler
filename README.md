# Bisnis.com Crawler

Crawler dan scraper artikel dari [bisnis.com](https://www.bisnis.com), ditulis dalam Python. Mendukung dua mode operasi: pengambilan artikel dalam rentang tanggal tertentu, dan pemantauan artikel terbaru secara berkala.

## Instalasi

```bash
pip install -r requirements.txt
```

---

## Fungsi Dasar

Crawler bekerja dalam dua langkah utama untuk setiap mode:

**1. Kumpulkan URL artikel**

Crawler mengidentifikasi URL artikel dari bisnis.com tanpa perlu membuka satu per satu halaman artikel terlebih dahulu. Setiap URL artikel bisnis.com mengandung tanggal terbit dalam formatnya sendiri: `.../read/YYYYMMDD/...`. Dengan pola ini, crawler bisa menyaring artikel berdasarkan rentang tanggal hanya dari URL-nya, tanpa biaya HTTP tambahan.

URL dikumpulkan dari tiga sumber berbeda tergantung kebutuhan:

- **Index** (`bisnis.com/index?page=N`) — halaman daftar artikel terbaru bisnis.com. Mencakup sekitar 4 hari terakhir. Setiap halaman berisi puluhan link artikel. Digunakan oleh mode Backtrack untuk tanggal yang dekat.
- **Search** (`search.bisnis.com/?q=Bisnis&page=N`) — mesin pencari internal bisnis.com. Mencakup arsip artikel hingga tahun 2016 dalam sekitar 6.280 halaman. Hasil pencarian dikemas sebagai `/link?url=ENCODED_URL`; crawler men-decode URL asli dari wrapper tersebut. Digunakan oleh mode Backtrack untuk tanggal yang lebih lama.
- **Sitemap** (`bisnis.com/sitemap-news.xml`) — file XML yang diperbarui secara real-time berisi artikel yang baru diterbitkan dalam 2-3 hari terakhir. Digunakan oleh mode Standard.

**2. Scrape isi artikel**

Setelah daftar URL terkumpul, crawler membuka setiap halaman artikel satu per satu dan mengekstrak:

- **Judul** — dari tag `<h1>`, atau fallback ke meta `og:title`
- **Tanggal terbit** — dicoba dari meta `article:published_time`, atribut `itemprop="datePublished"`, teks bertanggal di halaman (format Indonesia), lalu fallback ke tanggal dalam URL
- **Isi** — dicari dari kontainer konten artikel berdasarkan nama class (`konten`, `content`, `detail`, dll.), fallback ke tag `<article>`, lalu fallback ke semua paragraf `<p>` setelah `<h1>`

---

## Arsitektur

```
bisnis-crawler/
├── crawler/
│   ├── __init__.py
│   └── core.py        # modul bersama: semua logika HTTP, parsing, dan ekstraksi
├── backtrack.py       # entrypoint mode Backtrack
├── standard.py        # entrypoint mode Standard
└── requirements.txt
```

Kedua entrypoint mengimpor satu modul bersama: `crawler/core.py`. Modul ini berisi class `BisnisCrawler` yang menangani seluruh operasi yang dapat digunakan bersama — HTTP request dengan retry otomatis, parsing HTML, ekstraksi URL dari ketiga sumber, parsing tanggal format Indonesia, scraping isi artikel, dan penyimpanan JSON. Masing-masing entrypoint hanya berisi logika alur kerja spesifik untuk mode-nya.

```
backtrack.py          standard.py
     |                     |
     +-------+  +----------+
             |  |
        crawler/core.py  (class BisnisCrawler)
             |
     +-------+-----------+
     |         |         |
  /index   /sitemap   search.bisnis.com
```

**Cara pemilihan sumber di mode Backtrack:**

Jika rentang tanggal yang diminta masih dalam 4 hari terakhir, crawler menggunakan sumber `index`. Jika lebih lama dari itu, crawler beralih ke sumber `search` yang mencakup arsip penuh. Perilaku ini otomatis dengan `--source auto`, atau bisa dipaksa manual dengan `--source index` / `--source search`.

**Binary search untuk arsip lama:**

Saat menggunakan sumber search, crawler tidak menelusuri semua 6.280 halaman dari halaman pertama. Halaman-halaman search diurutkan dari artikel terbaru (halaman 1) hingga terlama (halaman 6.280). Crawler menjalankan binary search untuk menemukan halaman pertama yang mengandung artikel dalam rentang tanggal yang diminta, lalu mulai menelusuri dari sana ke halaman berikutnya. Ini membuat pengambilan arsip lama jauh lebih efisien.

---

## Mode A — Backtrack

Mengambil semua artikel yang terbit dalam rentang tanggal tertentu, lalu menyimpannya ke satu file JSON.

```bash
python backtrack.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

| Flag | Default | Keterangan |
|---|---|---|
| `--start-date` | wajib | Tanggal awal (inklusif), format `YYYY-MM-DD` |
| `--end-date` | wajib | Tanggal akhir (inklusif), format `YYYY-MM-DD` |
| `--output` | `backtrack_output.json` | Path file output |
| `--delay` | `1.0` | Jeda antar request dalam detik |
| `--source` | `auto` | `auto` / `index` / `search` |

**Pemilihan sumber (`--source`):**

| Nilai | Perilaku |
|---|---|
| `auto` | Pakai `index` jika rentang tanggal dalam 4 hari terakhir, pakai `search` jika lebih lama |
| `index` | Paksa pakai halaman index bisnis.com (cocok untuk artikel 1-4 hari terakhir) |
| `search` | Paksa pakai mesin pencari bisnis.com (cocok untuk arsip hingga tahun 2016, ~6.280 halaman) |

**Contoh:**

```bash
# Artikel beberapa hari terakhir
python backtrack.py --start-date 2026-06-06 --end-date 2026-06-08

# Artikel bulan lalu (otomatis pakai arsip pencarian)
python backtrack.py --start-date 2026-05-01 --end-date 2026-05-31

# Artikel dari tahun 2020
python backtrack.py --start-date 2020-06-01 --end-date 2020-06-30 --source search
```

---

## Mode B — Standard

Long-running process yang secara berkala mengambil artikel terbaru dari sitemap bisnis.com dan menambahkannya ke file JSON. Artikel yang sudah pernah diambil tidak akan diambil ulang antar siklus.

```bash
python standard.py
```

| Flag | Default | Keterangan |
|---|---|---|
| `--interval` | `300` | Interval pengambilan dalam detik |
| `--output` | `standard_output.json` | Path file output |
| `--delay` | `1.0` | Jeda antar request dalam detik |
| `--run-once` | nonaktif | Jalankan satu siklus lalu berhenti |

```bash
python standard.py --interval 120 --output terbaru.json
```

Tekan `Ctrl+C` untuk menghentikan. Proses akan menyelesaikan siklus yang sedang berjalan sebelum benar-benar berhenti.

---

## Format Output

Kedua mode menghasilkan array JSON dengan format:

```json
[
  {
    "link": "https://ekonomi.bisnis.com/read/20260607/44/1979061/judul-artikel",
    "title": "Judul Artikel",
    "content": "Paragraf pertama artikel.\n\nParagraf kedua artikel.",
    "published_at": "2026-06-07T21:17:00+07:00"
  }
]
```

| Field | Keterangan |
|---|---|
| `link` | URL lengkap artikel |
| `title` | Judul artikel |
| `content` | Isi lengkap artikel, paragraf dipisah dengan baris kosong |
| `published_at` | Waktu terbit dalam format ISO 8601, zona waktu WIB (UTC+7) |
