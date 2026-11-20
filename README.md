# Merchku — Flask E-Commerce (PBL#1)

Toko merch kampus: katalog + pencarian/filter, ukuran S–XXL, keranjang,
checkout + transfer manual (upload bukti bayar), chat customer–penjual,
ulasan/rating setelah pesanan selesai, dan dashboard admin.

## Tim & Pembagian Tugas

| Anggota | Peminatan | Tanggung jawab di proyek |
|---|---|---|
| **Dewi Fahera Ellyanti** | Web Fundamental | Ketua & pengembang utama aplikasi Flask: struktur *application factory* + blueprint, model SQLAlchemy & migration, login/register + hashing password, CRUD produk, katalog, dashboard admin, template Jinja2, validasi client-side & server-side (`app/`, `migrations/`, `app/templates/`, `app/static/js/form-validation.js`) |
| **Bram Lumazato Manao** | Internetworking | Deployment & jaringan: konfigurasi server (Gunicorn, Nginx, Passenger/PythonAnywhere), environment `.env`, database MySQL, topologi jaringan & akses domain/HTTPS (`config.py`, `passenger_wsgi.py`, `nginx-merchku.conf.example`, `gunicorn-merchku.service.example`, `scripts/sqlite_ke_mysql.py`) |
| **Keisha Bilqis Sabil** | — | Konten & UI/UX: data dan foto produk, tampilan katalog & halaman toko, data demo, serta pengujian fungsional fitur dari sisi pengguna (`product_photos/`, `app/static/css/`, `app/cli.py` seed data) |
| **Irene Selestial Purba** | SOC (Security Operations Center) | Logging & monitoring keamanan: format log event keamanan (login gagal, akses ditolak, perubahan data), analisis log, dan dokumentasi pengujian keamanan (`app/security_logger.py`, `docs/contoh-app.log`, `docs/UJI_KEAMANAN.md`) |
| **Justin** | Network Defender | Hardening & pengujian keamanan: security headers/CSP, proteksi CSRF, rate limiting, validasi upload & input (mis. menolak payload `{{7*7}}`), keamanan sesi, hardening server (`app/core/middleware.py`, `app/core/uploads.py`, `app/core/validators.py`, `docs/HARDENING_VM.md`, `tests/test_hardening.py`) |

## Fitur

| Modul | Rute | Keterangan |
|---|---|---|
| Katalog | `/katalog/` | Cari (`q`), filter kategori (`cat`), rentang harga (`minp`/`maxp`), sortir `terbaru`/`populer`/`termurah`/`termahal` |
| Detail & ulasan | `/katalog/<id>` | Rating 1–5, 1 ulasan per pengguna per produk, balasan penjual |
| Keranjang | `/keranjang/` | Tambah/ubah/hapus, batas jumlah per item, proteksi IDOR |
| Profil & alamat | `/profil/` | Data penerima dan alamat tersimpan untuk checkout; pelanggan tidak dapat mengubah role menjadi penjual |
| Checkout | `/pesanan/checkout` | Menampilkan alamat profil; tarif Biteship dihitung langsung jika API key dan kode pos asal tersedia |
| Pengiriman & pembayaran | `/pesanan/<id>` | Tarif Biteship menjadi bagian total; pembayaran Midtrans Snap diverifikasi lewat notifikasi |
| Bukti bayar | `/pesanan/<id>/upload-bukti` | JPG/PNG/PDF maks 2 MB untuk metode non-COD, disimpan di `uploads/private` |
| Chat | `/chat/` | Percakapan tersimpan antara customer dan penjual, dimulai dari halaman produk |
| Admin | `/admin/` | Dashboard, CRUD produk, kelola user, verifikasi bayar, laporan |
| Seller | `/seller/` | Kelola produk sendiri, balas ulasan, lihat pesanan |
| Ops | `/healthz`, `/metrics` | Health check dan metrik Prometheus (dilindungi token) |

Katalog dan halaman detail produk dapat dilihat tanpa login; pembeli yang sudah
login melihat katalog yang sama. Produk yang belum memiliki foto memakai
ilustrasi demo lokal sesuai kategori. Jalankan `flask seed-demo` untuk membuat
akun toko demo beserta katalog produk contoh; kredensial akun ditampilkan oleh
perintah tersebut.

Foto produk juga bisa disiapkan manual di folder `product_photos/` pada root
proyek. Foto boleh dikelompokkan ke subfolder kategori seperti `Almet`,
`Jaket`, `Kaos lengan pendek`, `Kaos lengan panjang`, `Stiker`, `Topi`,
`Totebag`, dan `Gantungan kunci`. Folder ekspor untuk `Hoodie`, `Lanyard`,
`Mug kampus`, `Notebook a5`, dan `Pin` juga didukung beserta subfoldernya.
File `.jpg`, `.jpeg`, dan `.png` di folder kategori akan dipakai bergiliran
untuk produk yang sesuai. Alternatifnya, letakkan foto langsung di folder
tersebut dengan nama `product-<ID>.jpg`, `product-<ID>.jpeg`, atau
`product-<ID>.png` (contoh: `product-3.jpg`). ID produk ada di kolom `#` pada
daftar produk admin/penjual. Jika produk memiliki foto yang diunggah lewat
dashboard, foto dashboard tetap dipakai; jika tidak, aplikasi mencari foto
manual lalu memakai ilustrasi kategori sebagai fallback.

Ukuran yang didukung: `S`, `M`, `L`, `XL`, `XXL`.

Data penerima disimpan di profil dan disalin sebagai snapshot saat checkout. Checkout mendukung tarif Biteship dan pembayaran Midtrans Snap saat kredensial tersedia. Tanpa kredensial, pilihan pengiriman/pembayaran manual tetap tersedia; COD tidak membutuhkan payment gateway.

Checkout menampilkan kurir, layanan, estimasi pengiriman, dan tarif dalam satu
pilihan. Rincian biaya layanan, diskon ongkir, dan perlindungan kemasan dapat
diatur melalui `CHECKOUT_SERVICE_FEE_RP`, `CHECKOUT_SHIPPING_DISCOUNT_RP`, dan
`FRAGILE_PACKING_FEE_RP`; semuanya bernilai Rp0 secara default. Penjual/admin
dapat menandai produk rawan pecah dan pembeli dapat memilih perlindungan
kemasan saat checkout. Produk pakaian mendukung informasi jenis dan warna.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
# edit .env, minimal SECRET_KEY (lihat catatan di bawah)
set FLASK_APP=run.py        # Windows
flask run
```

Buat akun admin pertama:

```bash
flask create-admin
```

Seed data demo (menolak jalan di production kecuali `--force`):

```bash
flask seed-demo
```

Akun seller demo: `seller@demo.test` / `SellerDemo1234`.

## Development

```bash
pip install -r requirements-dev.txt   # pytest, pytest-cov, ruff, bandit
pytest -q                             # jalankan test
ruff check .                          # lint
bandit -r app -x tests,migrations -ll # security scan
```

## Database

Untuk kebutuhan PBL, siapkan server MySQL atau MariaDB lokal dan buat database
`merchku` dengan charset `utf8mb4`. Proyek memakai driver PyMySQL. Di `.env`, isi
`DB_ENGINE=mysql`, host/port/user/password/nama database; konfigurasi membentuk
URL SQLAlchemy dan meng-encode kredensial dengan aman. Alternatifnya, isi
`SQLALCHEMY_DATABASE_URI` secara eksplisit. Jangan menaruh kredensial produksi di
Git. SQLite tetap tersedia untuk pengembangan ringan jika `DB_ENGINE=sqlite`.

Setelah database MySQL/MariaDB siap dan akun database memiliki akses ke database
tersebut, terapkan skema:

```bash
flask db upgrade
```

Pindah dari SQLite lama? Setelah `flask db upgrade` di MySQL, salin seluruh isinya:

```bash
python scripts/sqlite_ke_mysql.py            # dari instance/merchku.db
```

Catatan Windows: bila koneksi ke `127.0.0.1` ditolak padahal user sudah dibuat,
isi `DB_HOST=localhost`.

Atau isi data demo dari awal ke database yang sedang dikonfigurasi dengan:

```bash
flask seed-demo
```

Migrasi memakai Alembic (folder `migrations/`). `seed-demo` aman dijalankan
berulang: melengkapi profil demo yang kosong, menetapkan berat produk demo, dan
tidak menghapus data yang sudah ada. Pastikan database yang dipakai benar dengan
memeriksa `SQLALCHEMY_DATABASE_URI` sebelum migrasi atau seeding.

## Konfigurasi

Semua konfigurasi dibaca dari `.env` (lihat `.env.example`).

> **Penting:** ganti `SECRET_KEY=change-me` dan `METRICS_TOKEN=change-metrics-token`
> di `.env` sebelum dipakai di server. Di production, `SECRET_KEY` wajib diisi —
> aplikasi menolak start bila kosong. `SECRET_KEY` boleh diacak ulang di dev.

Untuk checkout terhubung, isi `BITESHIP_API_KEY`, `SHIPPING_ORIGIN_POSTAL_CODE`,
dan `MIDTRANS_SERVER_KEY` dari akun resmi. Gunakan Server Key sandbox Midtrans
untuk pengembangan dan biarkan `MIDTRANS_IS_PRODUCTION=0`; jangan commit atau
mengirim API key ke chat. Atur Payment Notification URL Midtrans ke
`/pesanan/webhooks/midtrans` di dashboard merchant. Berat produk diatur per
produk dan dipakai untuk permintaan tarif Biteship.

Variabel utama: `SECRET_KEY`, `SQLALCHEMY_DATABASE_URI`, `LOG_DIR`,
`TRUSTED_PROXIES`, `SECURE_COOKIES`, `METRICS_TOKEN`, `UPLOAD_PUBLIC`,
`UPLOAD_PRIVATE`, `MAX_CONTENT_LENGTH`, `RATE_LIMIT_DEFAULT`, `BITESHIP_API_KEY`,
`SHIPPING_ORIGIN_POSTAL_CODE`, `MIDTRANS_SERVER_KEY`, `MIDTRANS_IS_PRODUCTION`.

## Deployment

Contoh konfigurasi tersedia di `gunicorn-merchku.service.example` (systemd) dan
`nginx-merchku.conf.example` (reverse proxy).

> Catatan produksi: Flask-Limiter memakai storage in-memory secara default.
> Untuk multi-worker Gunicorn, set `RATELIMIT_STORAGE_URI` (mis.
> `redis://localhost:6379`) agar batas request konsisten antar worker.
