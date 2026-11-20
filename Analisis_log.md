# Analisis Log Keamanan Merchku

Analis: Irene Selestial Purba
Tanggal: 20 November 2026
Bagian: SOC (Security Operations Center)

## 1. Sumber Log
Aplikasi mencatat event keamanan dalam format JSON (satu baris = satu event)
ke file `logs/security.json` melalui `app/security_logger.py`.
File log otomatis dirotasi saat mencapai 10 MB (disimpan 5 cadangan).

Setiap baris log berisi: waktu (`timestamp`), jenis event (`event`), level
(`info`/`warning`), user (`user_id`, `email`, `role`), `ip`, `path`, `method`,
dan `user_agent`.

## 2. Event yang Dipantau
| Event | Level | Arti |
|---|---|---|
| login_success | info | Login berhasil |
| login_failed | warning | Login gagal (password salah / akun tidak ada) |
| account_locked | warning | Akun dikunci sementara karena terlalu banyak login gagal |
| access_denied | warning | User mencoba membuka halaman/data yang bukan haknya |
| file_upload_rejected | warning | Upload file ditolak (bukan gambar / terlalu besar) |
| produk_created / produk_updated / produk_deleted | info | Perubahan data produk |
| user_role_changed / user_status_changed | info | Admin mengubah role/status user |
| server_error | error | Terjadi error di server |

## 3. Hasil Analisis `docs/contoh-app.log`
| Event | Jumlah |
|---|---|
| login_success | 11 |
| access_denied | 10 |
| login_failed | 2 |
| file_upload_rejected | 2 |
| register_success | 1 |
| checkout_created | 1 |
| bukti_bayar_uploaded | 1 |
| order_status_changed | 1 |

Temuan:
- **access_denied (10 event):** user dengan role `customer` mencoba membuka
  pesanan dan keranjang milik user lain (`/pesanan/1`, `/pesanan/1/batalkan`,
  `/keranjang/ubah/1`). Semua ditolak dengan alasan `ownership`,
  artinya pengecekan kepemilikan data (anti-IDOR) berjalan.
- **login_failed (2 event):** jumlah masih wajar. Jika satu IP/email gagal
  berkali-kali dalam waktu singkat, sistem mengunci akun (`account_locked`)
  dan membatasi request (rate limiting).
- **file_upload_rejected (2 event):** file yang bukan gambar valid ditolak.

## 4. Insiden: Percobaan Template Injection
Ditemukan toko dengan nama `{{7*7}}sst` (user #536). Ini adalah payload uji
SSTI (Server-Side Template Injection). Hasil analisis:
- Nama tampil apa adanya (bukan `49sst`), artinya **serangan tidak berhasil**
  karena Jinja2 melakukan auto-escape.
- Tindak lanjut: tim menambahkan validasi nama toko & produk
  (`app/core/validators.py`) dan membersihkan data lama dengan perintah
  `flask bersihkan-nama-toko`.

## 5. Cara Memantau Log
Melihat 20 event terakhir:
    tail -n 20 logs/security.json

Mencari login gagal:
    grep '"login_failed"' logs/security.json

Menghitung jumlah tiap event:
    grep -o '"event": "[a-z_]*"' logs/security.json | sort | uniq -c | sort -rn

## 6. Rekomendasi
1. Cek `login_failed` dan `access_denied` secara rutin untuk mendeteksi
   brute force atau percobaan akses ilegal.
2. Beri perhatian khusus jika satu IP muncul berulang kali di event warning.
3. Simpan cadangan log secara berkala sebelum terhapus oleh rotasi.
