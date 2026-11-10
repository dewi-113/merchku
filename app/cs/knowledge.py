"""Pengetahuan toko untuk Customer Service Merchku.

Semua fakta di sini harus sesuai dengan fitur yang benar-benar ada di
aplikasi. Teks ini dipakai mesin jawaban otomatis dan sebagai system prompt
saat CS memakai Claude.
"""

STATUS_LABELS = {
    'menunggu_pembayaran': 'Menunggu pembayaran',
    'menunggu_verifikasi': 'Menunggu verifikasi pembayaran',
    'dibayar': 'Dibayar, sedang diproses penjual',
    'ditolak': 'Bukti bayar ditolak',
    'dikirim': 'Sedang dikirim',
    'selesai': 'Selesai',
    'dibatalkan': 'Dibatalkan',
}

COURIERS = 'JNE, J&T Express, SiCepat, AnterAja, dan Pos Indonesia'

SIZE_CHART = (
    'Panduan ukuran (cm) — Bahu / Dada ½ / Panjang / Lengan:\n'
    '• S: 40 / 47 / 66 / 57\n'
    '• M: 43 / 50 / 69 / 59\n'
    '• L: 46 / 53 / 72 / 61\n'
    '• XL: 49 / 56 / 75 / 63\n'
    '• XXL: 52 / 59 / 78 / 65\n'
    'Tips: bandingkan dengan baju yang paling pas kamu pakai.'
)

STORE_FACTS = f"""\
Merchku Store adalah marketplace merchandise kampus & komunitas (kaos, hoodie, jaket,
almamater, tote bag, stiker, lanyard, topi, mug, pin, notebook, gantungan kunci)
dari beberapa toko/penjual kampus.

CARA BELANJA
1. Masuk/daftar sebagai pembeli (akun penjual tidak bisa membeli).
2. Cari produk lewat kolom pencarian atau menu Jelajah/Katalog.
3. Di halaman produk pilih ukuran (untuk pakaian) dan jumlah, lalu
   "Tambah ke Keranjang" atau "Beli Sekarang".
4. Checkout: alamat diambil dari Profil (lengkapi dulu di menu Akun → Alamat
   pengiriman), pilih kurir dan metode pembayaran, lalu "Buat Pesanan".
5. Bayar, unggah bukti bayar bila metode manual, lalu pantau di Akun → Pesanan Saya.

PENGIRIMAN
- Kurir: {COURIERS}.
- Ongkir dihitung saat checkout; bila tarif otomatis belum aktif, ongkir
  dikonfirmasi oleh admin setelah pesanan dibuat.
- Barang mudah pecah (mis. mug) bisa memakai perlindungan kemasan tambahan.

PEMBAYARAN
- Transfer bank, QRIS, e-wallet (konfirmasi manual: unggah bukti bayar di
  halaman pesanan), atau COD (bayar tunai saat barang diterima).
- Bila pembayaran online aktif, tersedia pembayaran otomatis (QRIS, transfer,
  e-wallet) lewat Midtrans.

STATUS PESANAN
Menunggu pembayaran → Menunggu verifikasi (setelah bukti diunggah) → Dibayar →
Dikirim → Selesai. Jika bukti ditolak, statusnya "Bukti bayar ditolak" dan
pembeli bisa mengunggah ulang.

PEMBATALAN, RETUR & KOMPLAIN
- Pembeli bisa membatalkan sendiri pesanan berstatus "Menunggu pembayaran" atau
  "Bukti bayar ditolak" dari halaman detail pesanan.
- Belum ada fitur retur/refund otomatis. Untuk barang rusak/salah kirim,
  pembeli menghubungi penjual lewat fitur Chat Penjual (sertakan foto dan
  nomor pesanan) atau admin Merchku Store.

ULASAN
Ulasan & rating bisa diberikan setelah pesanan berstatus Selesai.

AKUN
- Penjual membuat akun penjual saat mendaftar (pilih "Penjual"); akun pembeli
  tidak bisa diubah menjadi akun penjual.
- Ganti password di Akun → Keamanan Akun (saat sudah login). Belum ada fitur
  lupa password otomatis; hubungi admin Merchku Store.
- Chat dengan penjual: tombol "Chat Penjual" di halaman produk atau toko
  (khusus akun pembeli).

{SIZE_CHART}
"""
