# Japanese LMS

Open-source MVP untuk belajar bahasa Jepang dengan materi JLPT N5–N3. Backend menggunakan FastAPI, SQLAlchemy async, dan PostgreSQL; antarmuka menggunakan Jinja2, HTMX, Tailwind CDN, serta Web Speech API.

## Menjalankan aplikasi

1. Siapkan Python 3.11+ dan PostgreSQL, lalu buat database `japanese_lms`.
2. Buat virtual environment dan pasang dependensi:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Salin `.env.example` menjadi `.env`, lalu sesuaikan `DATABASE_URL`.
4. Jalankan server:

   ```bash
   uvicorn app.main:app --reload
   ```

   Tabel MVP dibuat otomatis ketika aplikasi mulai berjalan.

5. Impor data Kanji N5–N3 dari API publik:

   ```bash
   python -m scripts.seed_from_api
   ```

   Untuk mengimpor level tertentu saja gunakan, misalnya, `--levels N5 N4`.

Buka `http://localhost:8000`. Halaman mencakup dashboard, daftar Kanji, pencarian/cache kosakata Jisho, materi tata bahasa, dan sesi flashcard dengan SRS sederhana. Identitas learner `demo` digunakan untuk progres lokal MVP; autentikasi dan administrasi materi belum termasuk.

API kanjiapi.dev dan Jisho diakses langsung saat dibutuhkan. Jisho menyimpan hasil pencarian di PostgreSQL; data Kanji disimpan oleh skrip seed. Tailwind CDN cocok untuk prototipe, bukan konfigurasi build produksi.
