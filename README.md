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

6. Impor data Kanji N5–N3 dari API publik:

   ```bash
   python -m scripts.seed_from_api
   ```

   Untuk mengimpor level tertentu saja gunakan, misalnya, `--levels N5 N4`.

Buka `http://localhost:8000`. Antarmuka tersedia dalam Bahasa Indonesia dan English; pilih bahasa dari menu di kanan atas dan preferensi disimpan di browser. Materi starter tata bahasa juga memiliki terjemahan Inggris, sementara materi lain yang belum diterjemahkan tetap ditampilkan dalam bahasa sumbernya.

Halaman mencakup beranda publik, dashboard siswa dan Sensei, daftar Kanji, pencarian/cache kosakata Jisho, materi tata bahasa, materi belajar, latihan, serta sesi flashcard SRS. Kanji dan tata bahasa dapat dicari pada semua data di level aktif, dengan 25 item per halaman; kosakata tersimpan juga memakai 25 item per halaman. Pencarian Jisho hanya berjalan setelah formulir dikirim dan mengikuti batas 10 item per halaman dari API. Materi tata bahasa starter adalah contoh awal, bukan daftar lengkap kurikulum JLPT.

## Autentikasi, role, dan dashboard

Pendaftaran dan masuk email/kata sandi menggunakan Neon Managed Auth di `/auth/signup`. Neon Auth menangani identitas, sedangkan Japango memverifikasi JWT EdDSA melalui JWKS dan menyimpan role aplikasi di tabel `app_users`. Akun baru selalu menjadi `student`; role yang dikirim dari browser atau JWT tidak digunakan sebagai sumber otorisasi. Cookie sesi aplikasi bersifat `HttpOnly`, `SameSite=Lax`, dan berlaku paling lama sampai JWT Neon Auth kedaluwarsa. Saat sesi perlu diperbarui, halaman login menukar token baru dan meneruskan pengguna ke halaman yang diminta.

### Konfigurasi lokal dan Vercel

1. Pastikan `neon.ts` mengaktifkan Auth, lalu jalankan `neon deploy` untuk branch Neon yang dipakai aplikasi.
2. Salin Auth URL branch tersebut ke `NEON_AUTH_BASE_URL`. `NEON_AUTH_JWKS_URL` boleh dikosongkan; Japango membentuk URL JWKS dari Auth URL. Jika Neon memberikan JWKS URL khusus, isi variabel tersebut.
3. Isi variabel yang sama pada Vercel → **Settings → Environment Variables** untuk setiap environment (Production, Preview, dan Development yang digunakan). Pastikan `DATABASE_URL` pada environment tersebut menunjuk ke branch Neon yang sama.
4. Tambahkan origin aplikasi (termasuk origin preview yang diperlukan) sebagai trusted domain Neon Auth. Contoh: `neon neon-auth domain add https://app.example.com`.
5. Karena bundle browser `app/static/auth.bundle.js` tidak disimpan di Git, atur **Build Command** Vercel menjadi `npm run build:auth` (Vercel memasang dependensi dari `package-lock.json`). Setelah deploy, pastikan `/static/auth.bundle.js` merespons dengan sukses. Untuk pengembangan lokal, jalankan `npm ci` lalu `npm run build:auth`.
6. Jalankan server dengan `uvicorn app.main:app --reload`. `Base.metadata.create_all()` membuat tabel tambahan untuk akun, kategori, materi, kuis, dan hasil pengerjaan saat aplikasi dimulai; baris progres demo lama tidak dipindahkan ke akun mana pun.

### Menjadikan pengguna Sensei

1. Pengguna mendaftar dan masuk setidaknya sekali. Akun aplikasi dibuat otomatis sebagai siswa.
2. Buka `/auth/signup` saat sudah masuk untuk melihat **Account ID** Neon Auth.
3. Jalankan skrip admin dengan `DATABASE_URL` yang menunjuk ke database/branch yang benar:

   ```bash
   python -m scripts.promote_sensei <AUTH_USER_ID>
   ```

Skrip hanya mempromosikan akun Japango yang sudah ada; role tidak dapat dipilih saat pendaftaran. Pastikan `DATABASE_URL` menunjuk ke branch yang benar sebelum menjalankan perintah.

Siswa hanya dapat melihat materi dan soal yang dipublikasikan, mengerjakan latihan, melihat progres dan riwayatnya sendiri. Sensei dapat mengelola kategori, materi, materi `Bunpou`, kuis dan pertanyaan, serta melihat progres dan hasil siswa. Pilihan ganda dinilai otomatis; jawaban tertulis menunggu penilaian Sensei. Kunci jawaban tidak dikirim ke halaman siswa.

### Pengujian alur

1. Jalankan `python -m unittest discover -s tests -v`.
2. Dengan Neon Auth aktif, uji daftar/masuk, muat ulang halaman, buka materi saat belum masuk, lalu keluar. Akses belajar tanpa sesi harus diarahkan ke login.
3. Masuk sebagai siswa: `/dashboard` harus mengarah ke `/student`; buka URL `/sensei` secara langsung untuk memastikan role siswa ditolak.
4. Promosikan akun uji menjadi Sensei, masuk ulang, lalu uji CRUD kategori, materi, Bunpou, dan kuis. Buat kuis pilihan ganda dan jawaban tertulis, kirim sebagai akun siswa, lalu nilai jawaban tertulis dari dashboard Sensei.
5. Pastikan akun siswa hanya dapat membuka riwayat pengerjaannya sendiri dan akun siswa lain tidak dapat melihat hasil tersebut.

Pengujian otomatis memverifikasi signature/audience/issuer/expiry JWT menggunakan kunci uji, pembatasan role, kepemilikan progres, CRUD inti, penilaian otomatis, dan penilaian manual. Alur Neon Auth langsung tetap perlu diuji dengan URL branch dan trusted domain yang dipakai di deployment.

Gloss bahasa Inggris dari kanjiapi.dev dan Jisho diterjemahkan ke Bahasa Indonesia melalui MyMemory saat diperlukan dan hasilnya disimpan di tabel `translation_cache`. Karena layanan gratis membatasi pemakaian anonim (5.000 karakter per hari), pemuatan pertama dapat lebih lambat; jika layanan gagal atau kuotanya habis, gloss Inggris ditampilkan dengan pemberitahuan. URL dan timeout layanan dapat diubah melalui `TRANSLATION_API_URL` dan `TRANSLATION_TIMEOUT_SECONDS`.

API kanjiapi.dev dan Jisho diakses langsung saat dibutuhkan. Jisho menyimpan hasil pencarian di PostgreSQL; data Kanji disimpan oleh skrip seed. Tailwind CDN cocok untuk prototipe, bukan konfigurasi build produksi.


