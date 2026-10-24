# Uji Keamanan Merchku (v1.0)

Ringkasan hasil pemeriksaan sebelum rilis v1.0 (PBL RKS 304).

## 1. Tes, ruff, bandit

| Pemeriksaan | Perintah | Hasil |
|---|---|---|
| Tes otomatis | `pytest -q` | 92 lulus, 0 gagal |
| Lint | `ruff check .` | 0 temuan |
| Keamanan kode | `bandit -r app -x tests,migrations` | 0 temuan |

Temuan bandit yang dibereskan:

- `urlopen` ke layanan eksternal sekarang hanya menerima alamat `https://`.
- SHA1 untuk nama file cache foto ditandai `usedforsecurity=False`.
- Password akun demo dan `random` di perintah seed diberi `# nosec` beserta
  alasannya. Perintah seed menolak berjalan di production.

## 2. Uji bobol sendiri

Setiap skenario dicoba sebagai pengguna yang sudah login terhadap data milik
pengguna lain. Hasil yang diharapkan: ditolak dan tercatat di log.

| Skenario | Tes | Hasil | Jejak di log |
|---|---|---|---|
| Ubah ID pesanan di URL ke pesanan orang lain (lihat detail) | `test_idor_order_detail` | 403 | `access_denied` (warning) |
| Batalkan pesanan orang lain | `test_idor_order_batalkan` | 403 | `access_denied` |
| Ubah / hapus item keranjang orang lain | `test_idor_cart_ubah`, `test_idor_cart_hapus` | 403 | `access_denied` |
| Lihat / unggah bukti bayar pesanan orang lain | `test_idor_serve_bukti`, `test_idor_upload_bukti` | 403 | `access_denied` |
| Manipulasi harga lewat field form | `test_harga_dari_db_bukan_form` | Harga tetap dari database | — |
| Jumlah melebihi stok | `test_checkout_tidak_oversell` | Ditolak | — |
| Bukti bayar palsu (berekstensi .jpg, isi bukan gambar) | `test_upload_file_palsu_ditolak` | Ditolak | `file_upload_rejected` (warning) |
| Foto profil palsu | `test_upload_avatar_palsu_ditolak` | Ditolak | `file_upload_rejected` |
| Bukti bayar asli | `test_upload_file_valid_sukses` | Diterima | `bukti_bayar_uploaded` |

Pertahanan yang membuat serangan gagal:

- **IDOR:** setiap route pesanan, keranjang, dan bukti bayar mengecek pemilik
  data sebelum menampilkan atau mengubahnya.
- **Harga:** harga dan total dihitung ulang di server dari tabel `products`.
  Nilai harga dari form tidak pernah dibaca.
- **Upload:** ekstensi, content-type, dan *magic bytes* dicek, ukuran dibatasi,
  lalu gambar di-encode ulang dengan Pillow dan disimpan dengan nama acak (UUID).
  Bukti bayar disimpan di folder privat.

## 3. Contoh log

[`contoh-app.log`](contoh-app.log) berisi log keamanan (format JSON per baris)
dari tes di atas. Upaya yang ditolak (`access_denied`, `file_upload_rejected`,
`login_failed`) tercatat dengan level `warning`. Log aplikasi asli ada di
`logs/security.json` (tidak ikut di Git).
