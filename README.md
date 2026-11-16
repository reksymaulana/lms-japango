# Japango

Japango adalah open-source MVP untuk belajar bahasa Jepang dengan materi JLPT N5–N3. Backend menggunakan FastAPI, SQLAlchemy async, dan PostgreSQL; antarmuka menggunakan Jinja2, HTMX, Tailwind CDN, serta Web Speech API.

## Menjalankan aplikasi

1. Siapkan Python 3.11+ dan PostgreSQL, lalu buat database `japanese_lms`.
2. Buat virtual environment dan pasang dependensi:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Salin `.env.example` menjadi `.env`, lalu sesuaikan `DATABASE_URL`. File `.env.local` juga dibaca dan dapat digunakan untuk nilai lokal yang menimpa `.env`; keduanya diabaikan Git.
4. Pasang dependensi frontend dan buat bundle Neon Auth:

   ```bash
   npm ci
   npm run build:auth
   ```

5. Jalankan server:

   ```bash
   uvicorn app.main:app --reload
   ```

   Tabel MVP dibuat otomatis ketika aplikasi mulai berjalan. Materi starter tata bahasa N5–N3 juga ditambahkan otomatis jika belum ada.

   Japango menggunakan SQLAlchemy async dengan `asyncpg`. URL PostgreSQL standar dari Neon (`postgresql://`) dikenali dan disesuaikan ke driver async; opsi `sslmode` juga diteruskan sebagai opsi SSL driver.

5. Impor data Kanji N5–N3 dari API publik:

   ```bash
   python -m scripts.seed_from_api
   ```

   Untuk mengimpor level tertentu saja gunakan, misalnya, `--levels N5 N4`.

Buka `http://localhost:8000`. Antarmuka tersedia dalam Bahasa Indonesia dan English; pilih bahasa dari menu di kanan atas dan preferensi disimpan di browser. Materi starter tata bahasa juga memiliki terjemahan Inggris, sementara materi lain yang belum diterjemahkan tetap ditampilkan dalam bahasa sumbernya.

Halaman mencakup dashboard, daftar Kanji, pencarian/cache kosakata Jisho, 18 pola tata bahasa starter N5–N3, dan sesi flashcard dengan SRS sederhana. Kanji dan tata bahasa dapat dicari pada semua data di level aktif, dengan 25 item per halaman; kosakata tersimpan juga memakai 25 item per halaman. Pencarian Jisho hanya berjalan setelah formulir dikirim dan mengikuti batas 10 item per halaman dari API. Materi tata bahasa ini adalah contoh awal, bukan daftar lengkap kurikulum JLPT. Pendaftaran/masuk tersedia melalui Neon Auth, tetapi progres MVP masih berupa progres demo bersama yang belum ditautkan ke akun; server menetapkan learner `demo` dan mengabaikan ID learner dari klien. Administrasi materi belum termasuk.

Pendaftaran dan masuk email/kata sandi tersedia di `/auth/signup` melalui Neon Managed Auth. Jalankan `neon deploy` untuk mengaktifkan Auth dan mengisi `NEON_AUTH_BASE_URL` pada file env lokal; bundle browser dibuat dengan `npm run build:auth`.

Gloss bahasa Inggris dari kanjiapi.dev dan Jisho diterjemahkan ke Bahasa Indonesia melalui MyMemory saat diperlukan dan hasilnya disimpan di tabel `translation_cache`. Karena layanan gratis membatasi pemakaian anonim (5.000 karakter per hari), pemuatan pertama dapat lebih lambat; jika layanan gagal atau kuotanya habis, gloss Inggris ditampilkan dengan pemberitahuan. URL dan timeout layanan dapat diubah melalui `TRANSLATION_API_URL` dan `TRANSLATION_TIMEOUT_SECONDS`.

API kanjiapi.dev dan Jisho diakses langsung saat dibutuhkan. Jisho menyimpan hasil pencarian di PostgreSQL; data Kanji disimpan oleh skrip seed. Tailwind CDN cocok untuk prototipe, bukan konfigurasi build produksi.


